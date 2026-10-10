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
from app.models import UsageEvent, db
from app.api.v1.chat import _resolve_text_model

log = logging.getLogger(__name__)

bp = Blueprint("vision", __name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
DEFAULT_MAX_OUTPUT_TOKENS = 2048

LAB_REPORT_SYSTEM_PROMPT = """شما یک دستیار هوش مصنوعی برای تحلیل برگه‌های آزمایش هستید.
کاربر تصویری از برگه آزمایش خود ارسال کرده است.

دستورالعمل:
1. مقادیر آزمایش را از تصویر بخوانید
2. هر مقدار را با رنج نرمال مقایسه کنید
3. موارد خارج از رنج را مشخص کنید (بالا/پایین)
4. به زبان ساده و فارسی توضیح دهید هر مورد چه معنایی دارد
5. در پایان حتماً این هشدار را بدهید: «این تحلیل صرفاً جهت اطلاع است و جایگزین نظر پزشک نیست. حتماً با پزشک خود مشورت کنید.»

لحن: ساده، همدلانه، بدون اصطلاحات پیچیده پزشکی."""


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

    if mode == "lab_report":
        system_prompt = LAB_REPORT_SYSTEM_PROMPT
        user_prompt = prompt or "این برگه آزمایش را تحلیل کن."
    else:
        system_prompt = "شما نورا، یک دستیار هوش مصنوعی فارسی‌زبان هستید. تصویر ارسال‌شده توسط کاربر را تحلیل کنید و به سؤال او پاسخ دهید."
        user_prompt = prompt or "این تصویر را توصیف و تحلیل کن."
        if len(user_prompt) > 2000:
            return validation_error()

    if rate_limited(f"ai:vision:{g.current_user_id}", 30, 3600):
        return error_response("RATE_LIMITED", status=429)

    model = _resolve_text_model(None)
    if model is None or not model.is_active:
        return error_response("MODEL_UNAVAILABLE", status=404)

    try:
        counter = TokenCounter(model.tokenizer_encoding) if model.tokenizer_encoding else None
    except TokenizerUnavailable:
        counter = None

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"
    provider_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    if counter is not None:
        text_tokens = counter.count_text(system_prompt) + counter.count_text(user_prompt)
    else:
        text_tokens = (len(system_prompt) + len(user_prompt)) // 4
    input_tokens = text_tokens + 1000

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

    try:
        result = provider.generate(model.provider_model_name, provider_messages, {"max_output_tokens": max_output})
    except Exception as exc:
        log.warning("vision provider failed: %s", exc)
        result = None

    if result is None or not result.ok:
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet, idempotency_key=f"vision:{idempotency_key}:reserve")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "تحلیل تصویر ناموفق بود.", 500)

    output_tokens = result.usage.get("output_tokens", max_output) if result.usage else max_output
    actual_input = result.usage.get("input_tokens", input_tokens) if result.usage else input_tokens
    try:
        final = pricing.estimate_text(model.id, actual_input, output_tokens)
        final_irr = final["total_irr"]
    except PricingRuleUnavailable:
        final_irr = estimated_irr

    usage.status = "succeeded"
    usage.final_input_tokens = actual_input
    usage.final_output_tokens = output_tokens
    usage.final_amount_irr = final_irr
    try:
        settle(
            db.session, wallet=wallet,
            idempotency_key=f"vision:{idempotency_key}:reserve",
            final_amount_irr=final_irr,
            reference_type="vision", reference_id=usage.id,
        )
    except Exception as exc:
        log.warning("vision settle failed: %s", exc)
    db.session.commit()

    return success_response({
        "analysis": result.text,
        "usage_event_id": usage.id,
    })
