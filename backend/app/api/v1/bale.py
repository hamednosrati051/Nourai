"""Bale messenger bot for Nourai.

Isolated blueprint — webhook receiver + command handlers. It only *reads*
shared services (billing ledger, AI providers, storage); it does not modify
any existing site code path.

Setup:
1. Add ``BALE_BOT_TOKEN`` to backend/.env (Hamed does this on the server).
2. Register the webhook once:
   POST https://tapi.bale.ai/bot<TOKEN>/setWebhook
   {"url": "https://inourai.ir/api/v1/bale/webhook"}

Commands:
  /start   — welcome + account linking
  /help    — command list
  /wallet  — wallet balance
  /image <prompt> — generate an image
  <text>   — chat with the AI
  <voice>  — transcribe to text
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
from app.billing.ledger import InsufficientBalance, get_wallet_for_update, release, reserve, settle
from app.billing.pricing import PricingRuleUnavailable, PricingService
from app.config import config
from app.extensions import db
from app.models import AiModel, MessengerUser, UsageEvent, User
from app.models.catalog import CAP_GENERATE_IMAGE, CAP_STT, CAP_TEXT
from app.models.messenger import PLATFORM_BALE
from app.services.users import get_user_by_mobile

log = logging.getLogger(__name__)

bp = Blueprint("bale", __name__, url_prefix="/bale")

BALE_API = "https://tapi.bale.ai"
TEXT_TIMEOUT = 90


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


def send_photo(chat_id: int, photo: bytes | str, caption: str | None = None,
               filename: str = "image.jpg") -> None:
    """Send a photo by bytes (multipart upload) or by URL."""
    if isinstance(photo, bytes):
        _bale_api("sendPhoto",
                  {"chat_id": str(chat_id), "caption": caption or ""},
                  files={"photo": (filename, photo, "image/jpeg")})
    else:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption
        _bale_api("sendPhoto", payload)


def download_bale_file(file_id: str) -> bytes | None:
    """Download a file (voice message) from Bale's servers."""
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
# Account linking
# ---------------------------------------------------------------------------

def _get_linked_user(bale_user_id: int) -> User | None:
    link = (
        db.session.query(MessengerUser)
        .filter_by(platform=PLATFORM_BALE, platform_user_id=bale_user_id)
        .first()
    )
    if link is None:
        return None
    return db.session.get(User, link.user_id)


def _link_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "📱 اشتراک شماره تماس", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def _handle_contact(chat_id: int, bale_user_id: int, contact: dict, from_user: dict) -> None:
    raw_phone = (contact or {}).get("phone_number", "")
    try:
        mobile = normalize_mobile(raw_phone)
    except ValueError:
        send_message(chat_id, "شماره تماس معتبر نیست. لطفاً دوباره تلاش کنید.")
        return
    user = get_user_by_mobile(db.session, mobile)
    if user is None or not user.is_active:
        send_message(
            chat_id,
            "این شماره در سایت نورا ثبت نشده.\n"
            "اول توی سایت ثبت‌نام کنید: https://inourai.ir\n"
            "بعد دوباره /start رو بزنید.",
        )
        return
    existing = (
        db.session.query(MessengerUser)
        .filter_by(platform=PLATFORM_BALE, platform_user_id=bale_user_id)
        .first()
    )
    if existing:
        existing.user_id = user.id
    else:
        db.session.add(MessengerUser(
            platform=PLATFORM_BALE,
            platform_user_id=bale_user_id,
            user_id=user.id,
            platform_username=(from_user or {}).get("username"),
            platform_first_name=(from_user or {}).get("first_name"),
        ))
    db.session.commit()
    send_message(
        chat_id,
        "✅ حسابت لینک شد!\n\n"
        "حالا می‌تونی:\n"
        "💬 متن بفرستی و با نورا چت کنی\n"
        "🎨 با /image یه توضیح بدی و عکس بگیری\n"
        "🎙️ ویس بفرستی تا به متن تبدیل بشه\n"
        "💰 با /wallet موجودیت رو ببینی",
    )


def _require_link(chat_id: int, bale_user_id: int, from_user: dict) -> User | None:
    user = _get_linked_user(bale_user_id)
    if user is None:
        send_message(
            chat_id,
            "سلام! 👋 به بات نورا خوش اومدی.\n\n"
            "برای استفاده، حسابت رو لینک کن — دکمه زیر رو بزن و شماره‌ت رو به اشتراک بذار:",
            reply_markup=_link_keyboard(),
        )
    return user


# ---------------------------------------------------------------------------
# Billing helpers
# ---------------------------------------------------------------------------

CHANNEL = "bale"  # source tag for usage events; telegram/eitaa use their own


def _record_usage(user_id: str, model_id: str, kind: str,
                  charged_irr: int, extra: dict | None = None) -> None:
    """Record a usage event tagged with the channel (bale/telegram/eitaa)."""
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
# Handlers
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
    # Rough token estimate for the hold (~4 chars/token).
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
        send_message(chat_id, "💰 موجودی کیف پولت کافی نیست. از سایت شارژ کن: https://inourai.ir")
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

    # Settle on actual usage when the provider reports it.
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
        send_message(chat_id, "💰 موجودی کیف پولت کافی نیست. از سایت شارژ کن: https://inourai.ir")
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

    # Store the audio so the STT provider can read it by key.
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

    # Rough duration estimate for the hold (ogg ~16kbps => bytes/2000 sec).
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
        send_message(chat_id, "💰 موجودی کیف پولت کافی نیست. از سایت شارژ کن: https://inourai.ir")
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
# Webhook
# ---------------------------------------------------------------------------

@bp.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    try:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        from_user = message.get("from") or {}
        bale_user_id = from_user.get("id")
        if not chat_id or not bale_user_id:
            return success_response({"ok": True})

        # Contact shared → link account.
        if message.get("contact"):
            _handle_contact(chat_id, bale_user_id, message["contact"], from_user)
            return success_response({"ok": True})

        text = (message.get("text") or "").strip()

        # Commands work without a linked account (they explain linking).
        if text.startswith("/start"):
            user = _get_linked_user(bale_user_id)
            if user:
                send_message(chat_id, "👋 خوش برگشتی! یه پیام بفرست تا شروع کنیم.")
            else:
                _require_link(chat_id, bale_user_id, from_user)
            return success_response({"ok": True})

        if text.startswith("/help"):
            send_message(chat_id,
                         "🤖 راهنمای بات نورا:\n\n"
                         "💬 متن بفرست → چت با هوش مصنوعی\n"
                         "🎨 /image + توضیح → تولید تصویر\n"
                         "🎙️ ویس بفرست → تبدیل به متن\n"
                         "💰 /wallet → موجودی کیف پول\n\n"
                         "شارژ کیف پول فقط از سایت: https://inourai.ir")
            return success_response({"ok": True})

        user = _require_link(chat_id, bale_user_id, from_user)
        if user is None:
            return success_response({"ok": True})

        if text.startswith("/wallet"):
            balance = _wallet_balance(user.id)
            send_message(chat_id, f"💰 موجودی کیف پولت: {_toman(balance)} تومان")
            return success_response({"ok": True})

        if text.startswith("/image"):
            _handle_image(chat_id, user, text[len("/image"):])
            return success_response({"ok": True})

        # Voice message → STT.
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
