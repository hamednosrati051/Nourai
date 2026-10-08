"""Bale messenger bot for Nourai.

Isolated blueprint — webhook receiver + command handlers. It only *reads*
shared services (billing ledger, AI providers, storage, payments); it does
not modify any existing site code path.

Design (per Hamed):
- Bot users are auto-provisioned on /start: a `users` row with NULL mobile
  + a standard wallet. Separate from site users, same wallet infrastructure.
- Phone sharing is optional (fills in mobile if provided, no gating).
- In-bot charging via Zibal: preset amounts -> gateway -> bot wallet.

Setup:
1. Add ``BALE_BOT_TOKEN`` to backend/.env (Hamed does this on the server).
2. Register the webhook once:
   POST https://tapi.bale.ai/bot<TOKEN>/setWebhook
   {"url": "https://inourai.ir/api/v1/bale/webhook"}
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import requests
from flask import Blueprint, request

from app.ai.adapters import get_image_provider, get_stt_provider, get_text_provider
from app.api.deps import success_response
from app.auth.otp import normalize_mobile
from app.billing.ledger import (
    InsufficientBalance,
    deposit,
    get_wallet_for_update,
    release,
    reserve,
    settle,
)
from app.billing.pricing import PricingRuleUnavailable, PricingService
from app.config import config
from app.extensions import db
from app.models import AiModel, MessengerUser, Payment, UsageEvent, User, WalletAccount
from app.models.catalog import CAP_GENERATE_IMAGE, CAP_STT, CAP_TEXT
from app.models.messenger import PLATFORM_BALE
from app.providers.zibal import ZibalNotConfigured, get_payment_gateway

log = logging.getLogger(__name__)

bp = Blueprint("bale", __name__, url_prefix="/bale")

BALE_API = "https://tapi.bale.ai"

# Preset top-up amounts in IRR (10k / 50k / 100k Toman).
CHARGE_PRESETS = [100_000, 500_000, 1_000_000]


# ---------------------------------------------------------------------------
# Bale API client
# ---------------------------------------------------------------------------

def _bale_token() -> str:
    token = (config.bale_bot_token or "").strip()
    if not token:
        raise RuntimeError("BALE_BOT_TOKEN is not configured")
    return token


def _bale_api(method: str, payload: dict | None = None, files: dict | None = None) -> dict:
    url = f"{BALE_API}/bot{_bale_token()}/{method}"
    try:
        if files:
            resp = requests.post(url, data=payload or {}, files=files, timeout=30)
        else:
            resp = requests.post(url, json=payload or {}, timeout=30)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("bale api %s failed: %s", method, exc)
        return {"ok": False, "error": str(exc)}
    return data


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _bale_api("sendMessage", payload)


def answer_callback(callback_id: str, text: str | None = None) -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    _bale_api("answerCallbackQuery", payload)


def send_photo(chat_id: int, photo: bytes, caption: str | None = None) -> None:
    _bale_api("sendPhoto",
              {"chat_id": str(chat_id), "caption": caption or ""},
              files={"photo": ("image.jpg", photo, "image/jpeg")})


def download_bale_file(file_id: str) -> bytes | None:
    info = _bale_api("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return None
    file_path = (info.get("result") or {}).get("file_path")
    if not file_path:
        return None
    url = f"{BALE_API}/file/bot{_bale_token()}/{file_path}"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:  # noqa: BLE001
        log.warning("bale file download failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# User provisioning (no phone required)
# ---------------------------------------------------------------------------

def _get_or_create_user(platform_user_id: int, from_user: dict) -> User:
    """Get the linked user, or auto-provision a new bot account."""
    link = (
        db.session.query(MessengerUser)
        .filter_by(platform=PLATFORM_BALE, platform_user_id=platform_user_id)
        .first()
    )
    if link:
        user = db.session.get(User, link.user_id)
        if user and user.is_active:
            return user
    # Auto-provision: users row with NULL mobile + wallet.
    user = User(mobile_normalized=None, is_active=True)
    db.session.add(user)
    db.session.flush()
    wallet = WalletAccount(user_id=user.id, balance_irr=0)
    db.session.add(wallet)
    db.session.add(MessengerUser(
        platform=PLATFORM_BALE,
        platform_user_id=platform_user_id,
        user_id=user.id,
        platform_username=(from_user or {}).get("username"),
        platform_first_name=(from_user or {}).get("first_name"),
    ))
    db.session.commit()
    log.info("bale auto-provisioned user %s for platform id %s", user.id, platform_user_id)
    return user


def _maybe_link_phone(user: User, raw_phone: str) -> bool:
    """Optionally fill in the mobile if the user shares their contact."""
    try:
        mobile = normalize_mobile(raw_phone)
    except ValueError:
        return False
    # Don't steal another account's number.
    taken = (
        db.session.query(User)
        .filter(User.mobile_normalized == mobile, User.id != user.id)
        .first()
    )
    if taken:
        return False
    user.mobile_normalized = mobile
    db.session.commit()
    return True


# ---------------------------------------------------------------------------
# Billing helpers
# ---------------------------------------------------------------------------

CHANNEL = "bale"


def _record_usage(user_id: str, model_id: str, kind: str,
                  charged_irr: int, extra: dict | None = None) -> None:
    meta = {"channel": CHANNEL, "kind": kind}
    if extra:
        meta.update(extra)
    db.session.add(UsageEvent(
        user_id=user_id,
        model_id=model_id,
        status="succeeded",
        charged_amount_irr=charged_irr,
        metadata_json=meta,
    ))


def _toman(amount_irr: int) -> str:
    return f"{amount_irr // 10:,}".replace(",", "٬")


def _wallet_balance(user_id: str) -> int:
    wallet = get_wallet_for_update(db.session, user_id)
    return wallet.balance_irr


# ---------------------------------------------------------------------------
# AI handlers (text / image / voice)
# ---------------------------------------------------------------------------

def _handle_text(chat_id: int, user: User, text: str) -> None:
    model = (
        db.session.query(AiModel)
        .filter_by(capability=CAP_TEXT, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )
    if model is None:
        send_message(chat_id, "مدل متنی فعالی پیدا نشد. بعداً تلاش کنید.")
        return
    try:
        provider = get_text_provider(model.provider_key, model)
    except ValueError as exc:
        log.error("bale text provider error: %s", exc)
        send_message(chat_id, "خطای سرویس. بعداً تلاش کنید.")
        return

    messages = [
        {"role": "system", "content": "You are Nourai (نورا), a helpful Persian AI assistant."},
        {"role": "user", "content": text},
    ]
    input_tokens = max(1, sum(len(m["content"]) for m in messages) // 4)
    max_output = 1024
    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_text(model.id, input_tokens, max_output)
    except PricingRuleUnavailable:
        send_message(chat_id, "تعرفه مدل تنظیم نشده. بعداً تلاش کنید.")
        return

    wallet = get_wallet_for_update(db.session, user.id)
    key = f"bale-text-{uuid.uuid4().hex}"
    try:
        reserve(db.session, wallet=wallet, amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_text_chat")
    except InsufficientBalance:
        send_message(chat_id, "💰 موجودیت کافی نیست. با /charge شارژ کن.")
        return
    db.session.commit()

    try:
        result = provider.generate(model.provider_model_name, messages, {"max_tokens": max_output})
    except Exception as exc:  # noqa: BLE001
        log.warning("bale text provider call failed: %s", exc)
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_text_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تولید پاسخ. بعداً تلاش کنید.")
        return

    if not result.ok:
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_text_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تولید پاسخ. بعداً تلاش کنید.")
        return

    out_tokens = result.output_tokens or max_output
    in_tokens = result.input_tokens or input_tokens
    try:
        final = pricing.estimate_text(model.id, in_tokens, out_tokens)["total_irr"]
    except PricingRuleUnavailable:
        final = estimate["total_irr"]
    settle(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
           final_amount_irr=final, idempotency_key=key, reason="bale_text_chat")
    _record_usage(user.id, model.id, "text", final,
                  {"input_tokens": in_tokens, "output_tokens": out_tokens})
    db.session.commit()
    send_message(chat_id, result.text or "پاسخی تولید نشد.")


def _handle_image(chat_id: int, user: User, prompt: str) -> None:
    prompt = (prompt or "").strip()
    if not prompt:
        send_message(chat_id, "بعد از /image توضیح عکست رو بنویس.\nمثال: /image یه غروب نارنجی روی دریا")
        return
    model = (
        db.session.query(AiModel)
        .filter_by(capability=CAP_GENERATE_IMAGE, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )
    if model is None:
        send_message(chat_id, "مدل تولید تصویر فعالی پیدا نشد.")
        return
    try:
        provider = get_image_provider(model.provider_key, model)
    except ValueError as exc:
        log.error("bale image provider error: %s", exc)
        send_message(chat_id, "خطای سرویس. بعداً تلاش کنید.")
        return

    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_image(model.id, image_count=1)
    except PricingRuleUnavailable:
        send_message(chat_id, "تعرفه مدل تنظیم نشده.")
        return

    wallet = get_wallet_for_update(db.session, user.id)
    key = f"bale-image-{uuid.uuid4().hex}"
    try:
        reserve(db.session, wallet=wallet, amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_image")
    except InsufficientBalance:
        send_message(chat_id, "💰 موجودیت کافی نیست. با /charge شارژ کن.")
        return
    db.session.commit()

    send_message(chat_id, "🎨 دارم عکست رو می‌سازم... چند لحظه صبر کن.")
    try:
        result = provider.generate(model.provider_model_name, prompt, {})
    except Exception as exc:  # noqa: BLE001
        log.warning("bale image provider call failed: %s", exc)
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_image_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تولید تصویر. بعداً تلاش کنید.")
        return

    if not result.ok or not result.image_bytes:
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_image_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تولید تصویر. بعداً تلاش کنید.")
        return

    settle(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
           final_amount_irr=estimate["total_irr"], idempotency_key=key, reason="bale_image")
    _record_usage(user.id, model.id, "image", estimate["total_irr"], {"image_count": 1})
    db.session.commit()
    send_message(chat_id, "🎨 عکست آماده شد!")
    send_photo(chat_id, result.image_bytes, caption=f"🎨 {prompt}")


def _handle_voice(chat_id: int, user: User, file_id: str) -> None:
    model = (
        db.session.query(AiModel)
        .filter_by(capability=CAP_STT, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )
    if model is None:
        send_message(chat_id, "مدل صوتی فعالی پیدا نشد.")
        return
    audio_bytes = download_bale_file(file_id)
    if not audio_bytes:
        send_message(chat_id, "دانلود ویس ناموفق بود. دوباره بفرست.")
        return

    from app.services.storage import storage  # lazy: avoids import cycles
    audio_key = f"bale-stt/{uuid.uuid4().hex}.ogg"
    try:
        storage.put_bytes(audio_key, audio_bytes, "audio/ogg")
    except Exception as exc:  # noqa: BLE001
        log.warning("bale voice storage failed: %s", exc)
        send_message(chat_id, "خطا در پردازش ویس.")
        return

    try:
        provider = get_stt_provider(model.provider_key, model)
    except ValueError as exc:
        log.error("bale stt provider error: %s", exc)
        send_message(chat_id, "خطای سرویس. بعداً تلاش کنید.")
        return

    est_seconds = max(1, len(audio_bytes) // 2000)
    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_audio(model.id, est_seconds)
    except PricingRuleUnavailable:
        send_message(chat_id, "تعرفه مدل تنظیم نشده.")
        return

    wallet = get_wallet_for_update(db.session, user.id)
    key = f"bale-stt-{uuid.uuid4().hex}"
    try:
        reserve(db.session, wallet=wallet, amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_stt")
    except InsufficientBalance:
        send_message(chat_id, "💰 موجودیت کافی نیست. با /charge شارژ کن.")
        return
    db.session.commit()

    try:
        result = provider.transcribe(model.provider_model_name, audio_key, {"language": "fa"})
    except Exception as exc:  # noqa: BLE001
        log.warning("bale stt call failed: %s", exc)
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_stt_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تبدیل صوت.")
        return

    if not result.ok:
        release(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
                idempotency_key=key, reason="bale_stt_failed")
        db.session.commit()
        send_message(chat_id, "خطا در تبدیل صوت.")
        return

    settle(db.session, wallet=wallet, reserved_amount_irr=estimate["total_irr"],
           final_amount_irr=estimate["total_irr"], idempotency_key=key, reason="bale_stt")
    _record_usage(user.id, model.id, "stt", estimate["total_irr"],
                  {"audio_seconds": est_seconds})
    db.session.commit()
    send_message(chat_id, f"🎙️ متن ویس:\n\n{result.text or 'متنی تشخیص داده نشد.'}")


# ---------------------------------------------------------------------------
# In-bot charging via Zibal
# ---------------------------------------------------------------------------

def _charge_keyboard() -> dict:
    buttons = [
        [{"text": f"💰 {_toman(a)} تومان", "callback_data": f"charge:{a}"}]
        for a in CHARGE_PRESETS
    ]
    return {"inline_keyboard": buttons}


def _handle_charge(chat_id: int, user: User) -> None:
    balance = _wallet_balance(user.id)
    send_message(
        chat_id,
        f"💰 موجودی فعلیت: {_toman(balance)} تومان\n\nمبلغ شارژ رو انتخاب کن:",
        reply_markup=_charge_keyboard(),
    )


def _handle_charge_callback(chat_id: int, callback_id: str, user: User, amount_irr: int) -> None:
    if amount_irr not in CHARGE_PRESETS:
        answer_callback(callback_id, "مبلغ نامعتبر")
        return
    # Create a Zibal payment for this bot user.
    payment = Payment(
        user_id=user.id,
        gateway="zibal",
        amount_irr=amount_irr,
        plan_id=None,
        status="created",
        idempotency_key=f"bale-pay-{uuid.uuid4().hex}",
    )
    db.session.add(payment)
    db.session.commit()

    try:
        gateway = get_payment_gateway()
        start = gateway.create_payment(
            amount_irr,
            "https://inourai.ir/api/v1/bale/payment-callback",
            {"payment_id": payment.id, "user_id": user.id, "channel": "bale",
             "chat_id": chat_id},
        )
    except ZibalNotConfigured:
        payment.status = "failed"
        payment.failure_message = "payment provider is not configured"
        db.session.commit()
        answer_callback(callback_id, "درگاه پرداخت تنظیم نشده")
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("bale payment create failed: %s", exc)
        payment.status = "failed"
        db.session.commit()
        answer_callback(callback_id, "خطا در ایجاد پرداخت")
        return

    payment.track_id = start.track_id
    payment.status = "pending"
    db.session.commit()
    answer_callback(callback_id)
    send_message(
        chat_id,
        f"💳 برای شارژ {_toman(amount_irr)} تومان، روی لینک زیر بزن و پرداخت کن:\n{start.payment_url}",
    )


@bp.get("/payment-callback")
def bale_payment_callback():
    """Zibal redirects here after a bot-initiated payment.

    Verifies with the gateway, credits the wallet, and notifies via Bale.
    """
    from flask import redirect
    track_id = request.args.get("track_id") or request.args.get("trackId")
    if not track_id:
        return redirect("https://ble.ir/nourai_bot", code=302)
    payment = db.session.query(Payment).filter_by(track_id=track_id).one_or_none()
    if payment is None:
        return redirect("https://ble.ir/nourai_bot", code=302)
    if payment.status == "paid":
        return redirect("https://ble.ir/nourai_bot", code=302)

    # Verify with gateway.
    try:
        gateway = get_payment_gateway()
        verification = gateway.verify_payment(track_id, payment.amount_irr)
    except Exception as exc:  # noqa: BLE001
        log.warning("bale payment verify failed: %s", exc)
        return redirect("https://ble.ir/nourai_bot", code=302)

    if not verification.paid:
        payment.status = "failed"
        db.session.commit()
        return redirect("https://ble.ir/nourai_bot", code=302)

    # Credit the wallet (idempotent).
    wallet = get_wallet_for_update(db.session, payment.user_id)
    try:
        deposit(
            db.session, wallet=wallet, amount_irr=payment.amount_irr,
            idempotency_key=f"payment:{payment.id}:deposit",
            reference_type="payment", reference_id=payment.id,
            description="bale bot top-up via zibal",
        )
    except Exception:  # noqa: BLE001
        log.info("bale payment %s already credited", payment.id)
    payment.status = "paid"
    db.session.commit()

    # Notify via Bale — in private chats, chat_id == platform_user_id.
    link = (
        db.session.query(MessengerUser)
        .filter_by(platform=PLATFORM_BALE, user_id=payment.user_id)
        .first()
    )
    if link:
        send_message(int(link.platform_user_id),
                     f"✅ {_toman(payment.amount_irr)} تومان به کیف پولت اضافه شد!")
    return redirect("https://ble.ir/nourai_bot", code=302)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@bp.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    try:
        # Callback queries (inline button taps).
        callback = update.get("callback_query") or {}
        if callback:
            cb_id = callback.get("id")
            from_user = callback.get("from") or {}
            bale_user_id = from_user.get("id")
            message = callback.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            data = (callback.get("data") or "")
            if bale_user_id and chat_id and data.startswith("charge:"):
                user = _get_or_create_user(bale_user_id, from_user)
                try:
                    amount = int(data.split(":", 1)[1])
                except ValueError:
                    amount = 0
                _handle_charge_callback(chat_id, cb_id, user, amount)
            else:
                answer_callback(cb_id)
            return success_response({"ok": True})

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        from_user = message.get("from") or {}
        bale_user_id = from_user.get("id")
        if not chat_id or not bale_user_id:
            return success_response({"ok": True})

        # Auto-provision on any interaction (no phone required).
        user = _get_or_create_user(bale_user_id, from_user)

        # Optional contact share → fill in mobile.
        if message.get("contact"):
            phone = (message["contact"] or {}).get("phone_number", "")
            if _maybe_link_phone(user, phone):
                send_message(chat_id, "📱 شمارت ثبت شد.")
            return success_response({"ok": True})

        text = (message.get("text") or "").strip()

        if text.startswith("/start"):
            send_message(
                chat_id,
                "👋 سلام! به بات نورا خوش اومدی.\n\n"
                "💬 متن بفرست → چت با هوش مصنوعی\n"
                "🎨 /image + توضیح → تولید تصویر\n"
                "🎙️ ویس بفرست → تبدیل به متن\n"
                "💰 /wallet → موجودی\n"
                "💳 /charge → شارژ کیف پول",
            )
            return success_response({"ok": True})

        if text.startswith("/help"):
            send_message(chat_id,
                         "🤖 راهنمای بات نورا:\n\n"
                         "💬 متن بفرست → چت با هوش مصنوعی\n"
                         "🎨 /image + توضیح → تولید تصویر\n"
                         "🎙️ ویس بفرست → تبدیل به متن\n"
                         "💰 /wallet → موجودی کیف پول\n"
                         "💳 /charge → شارژ کیف پول")
            return success_response({"ok": True})

        if text.startswith("/wallet"):
            balance = _wallet_balance(user.id)
            send_message(chat_id, f"💰 موجودی کیف پولت: {_toman(balance)} تومان")
            return success_response({"ok": True})

        if text.startswith("/charge"):
            _handle_charge(chat_id, user)
            return success_response({"ok": True})

        if text.startswith("/image"):
            _handle_image(chat_id, user, text[len("/image"):])
            return success_response({"ok": True})

        voice = message.get("voice") or {}
        if voice.get("file_id"):
            _handle_voice(chat_id, user, voice["file_id"])
            return success_response({"ok": True})

        if text:
            _handle_text(chat_id, user, text)
            return success_response({"ok": True})

        return success_response({"ok": True})
    except Exception as exc:  # noqa: BLE001
        log.exception("bale webhook failed: %s", exc)
        db.session.rollback()
        return success_response({"ok": True})
