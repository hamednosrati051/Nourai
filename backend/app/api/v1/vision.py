"""Image analysis (vision): send image + prompt to a vision-capable text model.

Uses the active text model (e.g. avalai-text/gpt-6-luna) which supports
image input via OpenAI-compatible chat completions.
"""
from __future__ import annotations

import base64
import logging

from flask import Blueprint, g, request

from app.ai.adapters import get_text_provider
from app.ai.tokens import TokenCounter, TokenizerUnavailable
from app.api.deps import (
    error_response,
    login_required,
    rate_limited,
    success_response,
    validation_error,
)
from app.billing.ledger import (
    DuplicateIdempotencyKey,
    InsufficientBalance,
    get_wallet_for_update,
    release,
    reserve,
    settle,
)
from app.billing.pricing import PricingService, PricingRuleUnavailable
from app.extensions import db
from app.models import AiModel, UsageEvent, VisionAnalysis
from app.api.v1.chat import _resolve_text_model


def _resolve_vision_model() -> AiModel | None:
    """Find active vision model, falling back to text model."""
    model = (
        db.session.query(AiModel)
        .filter_by(capability="vision", is_active=True)
        .first()
    )
    if model:
        return model
    # Fallback: use the active text model (existing behavior)
    return _resolve_text_model(None)

log = logging.getLogger(__name__)

bp = Blueprint("vision", __name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_MAX_OUTPUT_TOKENS = 2048
TOKENS_PER_IMAGE = 1000

LAB_REPORT_SYSTEM_PROMPT = """شما یک دستیار هوش مصنوعی برای تحلیل برگه‌های آزمایش هستید.
کاربر تصویری از برگه آزمایش خود ارسال کرده است.

مهم: اگر تصویر ارسالی برگه نتیجه یک آزمایش پزشکی نیست (مثلاً عکس شخصی، سند دیگر، تصویر نامرتبط)، آن را تحلیل نکن و فقط و فقط این جمله را برگردان:
تصویر شما مربوط به نتیجه یک آزمایش پزشکی نیست

خروجی باید دقیقاً این ساختار ۴ بخشی را داشته باشد:

### ۱. مشخصات و موضوع آزمایش
- نام آزمایش (فارسی + انگلیسی)
- روش انجام آزمایش (اگر در برگه ذکر شده)
- تاریخ آزمایش و سایر مشخصات مهم از برگه

---

### ۲. نتیجه آزمایش
- نتیجه شما (Result): مقدار دقیق
- بازه مرجع آزمایشگاه (Reference Interval): با ذکر جزئیات
- اگر جدول راهنما در برگه هست، خلاصه‌اش را بنویس

---

### ۳. تفسیر و نتیجه‌گیری
- در ۲-۳ جمله واضح بگو نتیجه چه معنایی دارد
- اگر نرمال است یا نه، صریح بگو

---

### ۴. نکات مهم
1. نکات مرتبط با زمان انجام آزمایش و دقت آن
2. اگر نتیجه غیرنرمال است، علل احتمالی را به زبان ساده بگو
3. توصیه نهایی: حتماً نتیجه را به پزشک نشان دهید

---

⚠️ این تحلیل صرفاً جهت اطلاع است و جایگزین نظر پزشک نیست.

قوانین:
- فارسی و ساده بنویس
- از همین عنوان‌های numbered استفاده کن (۱ تا ۴)
- اگر مقداری خوانا نبود بنویس «خوانا نبود»
- لحن همدلانه و حرفه‌ای"""


CONTRACT_SYSTEM_PROMPT = """شما یک دستیار هوش مصنوعی برای تحلیل قراردادهای ایرانی هستید.
کاربر تصویری از قرارداد خود ارسال کرده است.

مهم: اگر تصویر ارسالی یک قرارداد نیست (مثلاً عکس شخصی، برگه آزمایش، سند نامرتبط)، آن را تحلیل نکن و فقط و فقط این جمله را برگردان:
تصویر ارسالی شما یک قرارداد معتبر نیست

خروجی باید دقیقاً این ساختار ۵ بخشی را داشته باشد:

### ۱. مشخصات قرارداد
- نوع قرارداد (قولنامه، مبایعه‌نامه، اجاره‌نامه، قرارداد کار، و...)
- طرفین قرارداد (نام، کد ملی/شناسه ملی)
- موضوع قرارداد
- تاریخ تنظیم و مدت قرارداد
- مبلغ و نحوه پرداخت

---

### ۲. تعهدات کلیدی
- تعهدات طرف اول (فروشنده/موجر/کارفرما)
- تعهدات طرف دوم (خریدار/مستأجر/پیمانکار)
- شروط خاص (وجه التزام، خسارت تأخیر، و...)

---

### ۳. ریسک‌ها و نکات مشکل‌دار
- بندهای یک‌طرفه یا ناعادلانه
- ابهامات و نقاط ضعف متن
- مغایرت احتمالی با قوانین ایران
- برای قولنامه: بررسی کد رهگیری، استعلام ثبتی، بدهی‌های ملک

---

### ۴. بندهای جاافتاده
- مواردی که باید در قرارداد می‌بود ولی نیست
- مثلاً: شرط فسخ، داوری، وجه التزام، تاریخ تحویل دقیق

---

### ۵. توصیه‌ها
- ۳ تا ۵ توصیه عملی به زبان ساده

---

⚠️ **سلب مسئولیت:** این تحلیل صرفاً جهت اطلاع است و مشاوره حقوقی محسوب نمی‌شود. برای تصمیم‌گیری حقوقی حتماً با وکیل مشورت کنید.

قوانین:
- فارسی و ساده بنویس
- فقط بر اساس متن قرارداد نظر بده، حدس نزن
- اگر بخشی ناخواناست بنویس «ناخوانا»
- اعداد و تاریخ‌ها را دقیق نقل کن"""


@bp.post("/vision/analyze")
@login_required
def analyze_image():
    image_file = request.files.get("image")
    prompt = (request.form.get("prompt") or "").strip()
    mode = (request.form.get("mode") or "general").strip()

    if not image_file:
        return validation_error("image file is required")
    mime = image_file.content_type or ""
    if mime not in ALLOWED_MIME:
        return validation_error(f"unsupported image type: {mime}")
    image_bytes = image_file.read()
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return validation_error("image too large (max 10MB)")
    images = [(mime, image_bytes)]

    if mode == "lab_report":
        system_prompt = LAB_REPORT_SYSTEM_PROMPT
        user_prompt = prompt or "این برگه آزمایش را تحلیل کن."
    elif mode == "contract":
        system_prompt = CONTRACT_SYSTEM_PROMPT
        user_prompt = prompt or "این قرارداد را تحلیل کن."
    else:
        system_prompt = "شما نورا، یک دستیار هوش مصنوعی فارسی‌زبان هستید. تصویر ارسال‌شده توسط کاربر را تحلیل کنید و به سؤال او پاسخ دهید."
        user_prompt = prompt or "این تصویر را توصیف و تحلیل کن."
        if len(user_prompt) > 2000:
            return validation_error()

    if rate_limited(f"ai:vision:{g.current_user_id}", 30, 3600):
        return error_response("RATE_LIMITED", status=429)

    model = _resolve_vision_model()
    if model is None or not model.is_active:
        return error_response("MODEL_UNAVAILABLE", status=404)

    try:
        counter = TokenCounter(model.tokenizer_encoding) if model.tokenizer_encoding else None
    except TokenizerUnavailable:
        counter = None

    # Downscale images before sending: large phone photos choke the provider
    # (3+ full-size images return empty). Max 1568px on the long side, JPEG q85.
    def _prepare_image(image_bytes: bytes) -> tuple[str, bytes]:
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            w, h = img.size
            scale = min(1.0, 1568 / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return "image/jpeg", buf.getvalue()
        except Exception:
            return "image/jpeg", image_bytes

    b64_images = []
    for mime, b in images:
        out_mime, out_bytes = _prepare_image(b)
        b64_images.append((out_mime, base64.b64encode(out_bytes).decode("utf-8")))
    content_parts = [{"type": "text", "text": user_prompt}]
    for out_mime, b64 in b64_images:
        content_parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{out_mime};base64,{b64}"}}
        )
    provider_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_parts},
    ]

    if counter is not None:
        text_tokens = counter.count_text(system_prompt) + counter.count_text(user_prompt)
    else:
        text_tokens = (len(system_prompt) + len(user_prompt)) // 4
    input_tokens = text_tokens + TOKENS_PER_IMAGE

    max_output = DEFAULT_MAX_OUTPUT_TOKENS
    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_text(model.id, input_tokens, max_output)
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    try:
        provider = get_text_provider(model.provider_key, model)
    except ValueError as exc:
        log.error("vision provider misconfigured: %s", exc)
        return error_response("PROVIDER_ERROR", "AI provider is not configured.", 500)

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"vision:{idempotency_key}:reserve",
            reference_type="vision", reference_id=idempotency_key,
            description="reserve vision analysis",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    usage = UsageEvent(
        user_id=g.current_user_id,
        job_id=None,
        model_id=model.id,
        provider_key=model.provider_key,
        status="processing",
        est_input_tokens=input_tokens,
        est_output_tokens=max_output,
        estimated_amount_irr=estimated_irr,
    )
    db.session.add(usage)
    db.session.flush()

    def _call_provider():
        try:
            return provider.generate(model.provider_model_name, provider_messages, {"max_output_tokens": max_output})
        except Exception as exc:
            log.warning("vision provider failed: %s", exc)
            return None

    result = _call_provider()
    # Provider sometimes returns ok=True with empty text (e.g. choked on large
    # payloads). Retry once before giving up; never charge for an empty result.
    if result is not None and result.ok and not (result.text or "").strip():
        log.warning("vision provider returned empty text, retrying once")
        result = _call_provider()

    if result is None or not result.ok or not (result.text or "").strip():
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet,
                    reserved_amount_irr=estimated_irr,
                    idempotency_key=f"vision:{idempotency_key}:release")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "تحلیل تصویر ناموفق بود.", 500)

    output_tokens = result.output_tokens if result.output_tokens else max_output
    actual_input = result.input_tokens if result.input_tokens else input_tokens
    try:
        final = pricing.estimate_text(model.id, actual_input, output_tokens)
        final_irr = final["total_irr"]
    except PricingRuleUnavailable:
        final_irr = estimated_irr

    usage.status = "succeeded"
    usage.final_input_tokens = actual_input
    usage.final_output_tokens = output_tokens
    usage.final_amount_irr = final_irr
    usage.charged_amount_irr = final_irr
    try:
        settle(
            db.session, wallet=wallet,
            reserved_amount_irr=estimated_irr,
            idempotency_key=f"vision:{idempotency_key}:settle",
            final_amount_irr=final_irr,
            reference_type="vision", reference_id=usage.id,
        )
    except Exception as exc:
        log.warning("vision settle failed: %s", exc)

    # Save to history
    analysis = VisionAnalysis(
        user_id=g.current_user_id,
        mode=mode,
        prompt=user_prompt if mode == "general" else None,
        result_text=result.text,
        usage_event_id=usage.id,
        input_tokens=actual_input,
        output_tokens=output_tokens,
    )
    db.session.add(analysis)
    db.session.commit()

    return success_response({
        "analysis": result.text,
        "usage_event_id": usage.id,
    })


@bp.get("/vision/history")
@login_required
def vision_history():
    mode = request.args.get("mode", "lab_report")
    limit = min(int(request.args.get("limit", 20)), 50)
    items = (
        db.session.query(VisionAnalysis)
        .filter_by(user_id=g.current_user_id, mode=mode)
        .order_by(VisionAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    return success_response({
        "items": [
            {
                "id": a.id,
                "result_text": a.result_text,
                "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
            }
            for a in items
        ]
    })


CONTRACT_CHAT_SYSTEM_PROMPT = """شما یک دستیار حقوقی برای قراردادهای ایرانی هستید.

وظیفه شما:
- کمک به کاربر برای نوشتن پیش‌نویس قرارداد
- اصلاح و بهبود متن قراردادهای موجود
- پاسخ به سؤالات حقوقی مرتبط با قراردادها

قوانین:
- فقط درباره قراردادها و مسائل حقوقی مرتبط صحبت کن
- اگر کاربر سؤال غیرمرتبط پرسید، مؤدبانه بگو فقط در زمینه قرارداد کمک می‌کنی
- فارسی و ساده بنویس
- در پایان هر پاسخ مهم یادآوری کن: این مشاوره حقوقی نیست

⚠️ این مشاوره حقوقی محسوب نمی‌شود. برای تصمیم‌گیری حقوقی حتماً با وکیل مشورت کنید."""


@bp.get("/vision/contract-chat/history")
@login_required
def contract_chat_history():
    """List past contract chat sessions."""
    from app.models.contract_chat import ContractChatSession
    limit = min(int(request.args.get("limit", 20)), 50)
    sessions = (
        db.session.query(ContractChatSession)
        .filter_by(user_id=g.current_user_id)
        .order_by(ContractChatSession.created_at.desc())
        .limit(limit)
        .all()
    )
    return success_response({
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
            }
            for s in sessions
        ]
    })


@bp.get("/vision/contract-chat/history/<session_id>")
@login_required
def contract_chat_session_detail(session_id: str):
    """Get messages of a specific chat session."""
    from app.models.contract_chat import ContractChatSession, ContractChatMessage
    session = db.session.get(ContractChatSession, session_id)
    if not session or session.user_id != g.current_user_id:
        return error_response("NOT_FOUND", status=404)
    messages = (
        db.session.query(ContractChatMessage)
        .filter_by(session_id=session_id)
        .order_by(ContractChatMessage.created_at.asc())
        .all()
    )
    return success_response({
        "id": session.id,
        "title": session.title,
        "messages": [
            {"role": m.role, "content": m.content}
            for m in messages
        ],
    })


@bp.post("/vision/contract-chat")
@login_required
def contract_chat():
    """Simple contract assistant chat (no conversation management)."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []

    if not message:
        return validation_error("message is required")
    if len(message) > 5000:
        return validation_error("message too long")

    if rate_limited(f"ai:contract-chat:{g.current_user_id}", 30, 3600):
        return error_response("RATE_LIMITED", status=429)

    # Use the active text model
    from app.models import AiModel
    model = db.session.query(AiModel).filter_by(capability="text", is_active=True).first()
    if model is None:
        return error_response("MODEL_UNAVAILABLE", status=404)

    # Build messages
    provider_messages = [{"role": "system", "content": CONTRACT_CHAT_SYSTEM_PROMPT}]
    for h in history[-10:]:  # Last 10 messages
        if h.get("role") in ("user", "assistant") and h.get("content"):
            provider_messages.append({"role": h["role"], "content": h["content"][:2000]})
    provider_messages.append({"role": "user", "content": message})

    # Estimate tokens
    total_text = CONTRACT_CHAT_SYSTEM_PROMPT + message + "".join(h.get("content", "") for h in history[-10:])
    input_tokens = len(total_text) // 4 + 500
    max_output = 2048

    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_text(model.id, input_tokens, max_output)
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    try:
        provider = get_text_provider(model.provider_key, model)
    except ValueError as exc:
        log.error("contract chat provider misconfigured: %s", exc)
        return error_response("PROVIDER_ERROR", "AI provider is not configured.", 500)

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"contract-chat:{idempotency_key}:reserve",
            reference_type="contract_chat", reference_id=idempotency_key,
            description="reserve contract chat",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    usage = UsageEvent(
        user_id=g.current_user_id,
        job_id=None,
        model_id=model.id,
        provider_key=model.provider_key,
        status="processing",
        est_input_tokens=input_tokens,
        est_output_tokens=max_output,
        estimated_amount_irr=estimated_irr,
    )
    db.session.add(usage)
    db.session.flush()

    try:
        result = provider.generate(model.provider_model_name, provider_messages, {"max_tokens": max_output})
    except Exception as exc:
        log.warning("contract chat provider failed: %s", exc)
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet, idempotency_key=f"contract-chat:{idempotency_key}:reserve")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "خطا در تولید پاسخ.", 500)

    if result is None or not result.ok:
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet, idempotency_key=f"contract-chat:{idempotency_key}:reserve")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "خطا در تولید پاسخ.", 500)

    # Settle billing
    output_tokens = result.output_tokens if result.output_tokens else max_output
    actual_input = result.input_tokens if result.input_tokens else input_tokens
    try:
        final = pricing.estimate_text(model.id, actual_input, output_tokens)
        final_irr = final["total_irr"]
    except PricingRuleUnavailable:
        final_irr = estimated_irr

    usage.status = "succeeded"
    usage.final_input_tokens = actual_input
    usage.final_output_tokens = output_tokens
    usage.final_amount_irr = final_irr
    usage.charged_amount_irr = final_irr
    try:
        settle(
            db.session, wallet=wallet,
            reserved_amount_irr=estimated_irr,
            idempotency_key=f"contract-chat:{idempotency_key}:settle",
            final_amount_irr=final_irr,
            reference_type="contract_chat", reference_id=idempotency_key,
        )
    except Exception as exc:
        log.warning("contract chat settle failed: %s", exc)

    # Save to conversation history (non-blocking: chat must work even if this fails)
    _session_id = None
    try:
        from app.models.contract_chat import ContractChatSession, ContractChatMessage
        session_id = data.get("session_id")
        if session_id:
            session = db.session.get(ContractChatSession, session_id)
            if not session or session.user_id != g.current_user_id:
                session = None
        else:
            session = None
        if not session:
            title = message[:80] if len(message) <= 80 else message[:77] + "..."
            session = ContractChatSession(user_id=g.current_user_id, title=title)
            db.session.add(session)
            db.session.flush()
        db.session.add(ContractChatMessage(session_id=session.id, role="user", content=message))
        db.session.add(ContractChatMessage(session_id=session.id, role="assistant", content=result.text))
        db.session.commit()
        _session_id = session.id
    except Exception:
        db.session.rollback()
        log.warning("contract chat history save failed", exc_info=True)

    return success_response({"reply": result.text, "session_id": _session_id})
