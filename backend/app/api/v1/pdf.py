"""AI PDF generation: user gives an idea/topic (or ready text), gets back a Persian PDF.

Two modes:
  - "idea": AI drafts the full document from the topic, then renders PDF.
  - "text": AI only formats/structures the user's ready text, then renders PDF.

Billing follows the text-model tariff (input + output tokens), same as chat.
"""
from __future__ import annotations

import io
import logging
import uuid

from flask import Blueprint, g, request, send_file

from app.ai.adapters import get_text_provider
from app.ai.tokens import TokenCounter, TokenizerUnavailable
from app.api.deps import (
    error_response,
    login_required,
    rate_limited,
    success_response,
    validation_error,
)
from app.api.v1.chat import _resolve_text_model
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
from app.models import AiModel, UsageEvent
from app.services.pdf_generator import generate_pdf

log = logging.getLogger(__name__)

bp = Blueprint("pdf", __name__)

# Output token budgets per length choice
LENGTH_TOKENS = {
    "short": 1500,
    "medium": 4000,
    "long": 8000,
}

PDF_SYSTEM_PROMPT = """شما یک نویسنده حرفه‌ای فارسی‌زبان هستید که سندهای رسمی و مرتب تولید می‌کنید.

قوانین خروجی (حتماً رعایت شود):
- متن کاملاً فارسی، رسمی و روان باشد.
- ساختار با سرفصل‌های مشخص: از «## » برای عنوان بخش‌ها استفاده کنید.
- برای لیست‌ها از «- » در ابتدای خط استفاده کنید.
- پاراگراف‌ها کوتاه و خوانا باشند.
- در پایان یک بخش «## نتیجه‌گیری» اضافه کنید.
- هیچ توضیح اضافه درباره خودتان ندهید؛ فقط متن سند را بنویسید.
"""

FORMAT_SYSTEM_PROMPT = """شما یک ویراستار حرفه‌ای فارسی‌زبان هستید. متن کاربر را بگیرید و آن را به یک سند مرتب و ساخت‌یافته تبدیل کنید.

قوانین خروجی (حتماً رعایت شود):
- محتوای کاربر را تغییر ندهید؛ فقط ساختار، سرفصل و قالب‌بندی را بهبود دهید.
- از «## » برای عنوان بخش‌ها استفاده کنید.
- برای لیست‌ها از «- » در ابتدای خط استفاده کنید.
- متن کاملاً فارسی و راست‌چین‌دوستانه باشد.
- هیچ توضیح اضافه درباره خودتان ندهید؛ فقط متن سند را بنویسید.
"""


@bp.post("/pdf/generate")
@login_required
def pdf_generate():
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("mode", "idea")
    content = (data.get("content") or "").strip()
    length = data.get("length", "medium")
    title = (data.get("title") or "").strip()

    if mode not in ("idea", "text"):
        return validation_error("mode must be 'idea' or 'text'")
    if not content:
        return validation_error("content is required")
    if len(content) > 10000:
        return validation_error("content too long (max 10000 chars)")
    if length not in LENGTH_TOKENS:
        return validation_error("length must be short, medium or long")

    if rate_limited(f"ai:pdf:{g.current_user_id}", 10, 3600):
        return error_response("RATE_LIMITED", status=429)

    model = _resolve_text_model(None)
    if model is None or not model.is_active:
        return error_response("MODEL_UNAVAILABLE", status=404)

    max_output = LENGTH_TOKENS[length]

    if mode == "idea":
        system_prompt = PDF_SYSTEM_PROMPT
        user_prompt = (
            f"موضوع سند: {content}\n\n"
            f"یک سند کامل و ساخت‌یافته درباره این موضوع بنویس."
        )
    else:
        system_prompt = FORMAT_SYSTEM_PROMPT
        user_prompt = f"متن کاربر برای قالب‌بندی:\n\n{content}"

    if not title:
        title = content[:60]

    try:
        counter = TokenCounter(model.tokenizer_encoding) if model.tokenizer_encoding else None
    except TokenizerUnavailable:
        counter = None

    if counter is not None:
        text_tokens = counter.count_text(system_prompt) + counter.count_text(user_prompt)
    else:
        text_tokens = (len(system_prompt) + len(user_prompt)) // 4
    input_tokens = text_tokens

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
        log.error("pdf provider misconfigured: %s", exc)
        return error_response("PROVIDER_ERROR", "AI provider is not configured.", 500)

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"pdf:{idempotency_key}:reserve",
            reference_type="pdf", reference_id=idempotency_key,
            description="reserve pdf generation",
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

    provider_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = provider.generate(
            model.provider_model_name, provider_messages,
            {"max_output_tokens": max_output},
        )
    except Exception as exc:
        log.warning("pdf provider failed: %s", exc)
        result = None

    if result is None or not result.ok:
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet, idempotency_key=f"pdf:{idempotency_key}:reserve")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "تولید PDF ناموفق بود.", 500)

    output_tokens = result.output_tokens if result.output_tokens else max_output
    actual_input = result.input_tokens if result.input_tokens else input_tokens
    try:
        final = pricing.estimate_text(model.id, actual_input, output_tokens)
        final_irr = final["total_irr"]
    except PricingRuleUnavailable:
        final_irr = estimated_irr

    # Render PDF
    try:
        pdf_bytes = generate_pdf(title, result.text)
    except Exception as exc:
        log.error("pdf render failed: %s", exc)
        usage.status = "failed"
        try:
            release(db.session, wallet=wallet, idempotency_key=f"pdf:{idempotency_key}:reserve")
        except Exception:
            pass
        db.session.commit()
        return error_response("PROVIDER_ERROR", "ساخت فایل PDF ناموفق بود.", 500)

    usage.status = "succeeded"
    usage.final_input_tokens = actual_input
    usage.final_output_tokens = output_tokens
    usage.final_amount_irr = final_irr
    try:
        settle(
            db.session, wallet=wallet,
            idempotency_key=f"pdf:{idempotency_key}:reserve",
            final_amount_irr=final_irr,
            reference_type="pdf", reference_id=usage.id,
        )
    except Exception as exc:
        log.warning("pdf settle failed: %s", exc)
    db.session.commit()

    filename = f"nourai-pdf-{uuid.uuid4().hex[:8]}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
