"""AI PDF generation: two-step flow.

Step 1 (prepare): user gives an idea/topic (or ready text), AI drafts/formats
the document text and returns it as JSON for the user to review/edit.
  - "idea": AI drafts the full document from the topic.
  - "text": AI only formats/structures the user's ready text.

Step 2 (render): user sends the (possibly edited) text, backend renders the
Persian PDF, stores it in object storage + history, and returns the file.

Billing follows the text-model tariff (input + output tokens), same as chat,
and happens only at the prepare step. Rendering is free.

History: GET /pdf/history lists the user's documents; GET /pdf/<id>/download
re-downloads a stored file.
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
from app.models import AiModel, PdfDocument, UsageEvent, new_uuid
from app.services.pdf_generator import generate_pdf
from app.services.storage import StorageService, asset_key

log = logging.getLogger(__name__)

bp = Blueprint("pdf", __name__)

# Output token budgets per length choice (for billing estimation only)
LENGTH_TOKENS = {
    "short": 1500,
    "medium": 4000,
    "long": 8000,
}

# Human-readable length guidance injected into the prompt
LENGTH_GUIDANCE = {
    "short": "متن کوتاه باشد: حدود ۱ تا ۲ صفحه.",
    "medium": "متن با طول متوسط باشد: حدود ۳ تا ۵ صفحه.",
    "long": "متن بلند و مفصل باشد: حدود ۸ تا ۱۰ صفحه.",
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


def _default_title(title: str, content: str) -> str:
    title = (title or "").strip()
    if title:
        return title[:255]
    # Fallback: first 60 chars of the request text
    fallback = " ".join(content.split())[:60].strip()
    return fallback or "سند بدون عنوان"


@bp.post("/pdf/prepare")
@login_required
def pdf_prepare():
    """Step 1: AI drafts/formats the document text. Returns JSON {text, title}."""
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

    model = _resolve_text_model(None)
    if model is None or not model.is_active:
        return error_response("MODEL_UNAVAILABLE", status=404)

    max_output = LENGTH_TOKENS[length]

    if mode == "idea":
        system_prompt = PDF_SYSTEM_PROMPT
        user_prompt = (
            f"موضوع سند: {content}\n\n"
            f"یک سند کامل و ساخت‌یافته درباره این موضوع بنویس.\n"
            f"{LENGTH_GUIDANCE[length]}"
        )
    else:
        system_prompt = FORMAT_SYSTEM_PROMPT
        user_prompt = (
            f"متن کاربر برای قالب‌بندی:\n\n{content}\n\n"
            f"{LENGTH_GUIDANCE[length]}"
        )

    title = _default_title(title, content)

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
            {},  # no max_output_tokens: length is guided via prompt text
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
        return error_response("PROVIDER_ERROR", "تولید متن ناموفق بود.", 500)

    if not (result.text or "").strip():
        log.warning(
            "pdf prepare empty text: model=%s provider=%s max_output=%s input_tokens=%s output_tokens=%s",
            model.display_name, model.provider_key, max_output,
            result.input_tokens, result.output_tokens,
        )

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
    try:
        settle(
            db.session, wallet=wallet,
            reserved_amount_irr=estimated_irr,
            idempotency_key=f"pdf:{idempotency_key}:reserve",
            final_amount_irr=final_irr,
            reference_type="pdf", reference_id=usage.id,
        )
    except Exception as exc:
        log.warning("pdf settle failed: %s", exc)
    db.session.commit()

    return success_response({"text": result.text, "title": title})


@bp.post("/pdf/render")
@login_required
def pdf_render():
    """Step 2: render the (possibly edited) text to PDF, store it, return file."""
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    title = (data.get("title") or "").strip()

    if not text:
        return validation_error("text is required")
    if len(text) > 60000:
        return validation_error("text too long (max 60000 chars)")

    title = _default_title(title, text)

    try:
        pdf_bytes = generate_pdf(title, text)
    except Exception as exc:
        log.error("pdf render failed: %s", exc)
        return error_response("PROVIDER_ERROR", "ساخت فایل PDF ناموفق بود.", 500)

    # Store in object storage + history
    doc_id = new_uuid()
    key = asset_key(g.current_user_id, "pdf", "pdf")
    try:
        StorageService().put_bytes(key, pdf_bytes, "application/pdf")
    except Exception as exc:
        log.error("pdf storage failed: %s", exc)
        return error_response("PROVIDER_ERROR", "ذخیره فایل PDF ناموفق بود.", 500)

    doc = PdfDocument(
        id=doc_id,
        user_id=g.current_user_id,
        title=title,
        storage_key=key,
    )
    db.session.add(doc)
    db.session.commit()

    filename = f"nourai-pdf-{doc_id[:8]}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@bp.get("/pdf/history")
@login_required
def pdf_history():
    """List the user's generated PDF documents (latest 50)."""
    docs = (
        db.session.query(PdfDocument)
        .filter(PdfDocument.user_id == g.current_user_id)
        .order_by(PdfDocument.created_at.desc())
        .limit(50)
        .all()
    )
    return success_response({
        "items": [
            {
                "id": d.id,
                "title": d.title,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    })


@bp.get("/pdf/<doc_id>/download")
@login_required
def pdf_download(doc_id: str):
    """Re-download a stored PDF from history."""
    doc = (
        db.session.query(PdfDocument)
        .filter(
            PdfDocument.id == doc_id,
            PdfDocument.user_id == g.current_user_id,
        )
        .first()
    )
    if doc is None:
        return error_response("NOT_FOUND", status=404)

    try:
        pdf_bytes = StorageService().get_bytes(doc.storage_key)
    except Exception as exc:
        log.error("pdf download failed: %s", exc)
        return error_response("PROVIDER_ERROR", "دریافت فایل ناموفق بود.", 500)

    filename = f"nourai-pdf-{doc.id[:8]}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
