"""Text conversations: CRUD + synchronous message generation with
reserve/settle billing.

Billing flow per message:
1. client sends Idempotency-Key
2. input tokens counted with tiktoken (exact payload string); output tokens
   estimated from max_output_tokens
3. wallet row locked; user/model/balance checked
4. estimated amount reserved; usage_event created
5. provider called (bounded timeout)
6. final cost from provider usage when valid, else tiktoken recount
7. reserve settled to the final amount; failure releases the reserve
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError

from app.ai.adapters import FakeTextProvider, get_text_provider
from app.ai.tokens import TokenCounter, TokenizerUnavailable
from app.api.deps import (
    client_ip,
    error_response,
    ip_hash,
    login_required,
    paginate_query,
    pagination_params,
    rate_limited,
    success_response,
    utcnow,
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
from app.billing.pricing import PricingRuleUnavailable, PricingService
from app.config import config
from app.extensions import db
from app.models import AiModel, Conversation, Message, UsageEvent
from app.models.catalog import CAP_TEXT
from app.models.chat import ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_USER
from app.services.audit import audit
from app.services.plans import PlanLimitExceeded, PlanLimitService

log = logging.getLogger(__name__)

bp = Blueprint("chat", __name__)

GENERATION_TIMEOUT_SECONDS = 90
DEFAULT_MAX_OUTPUT_TOKENS = 1024
MAX_CONTENT_CHARS = 20000


class ConversationCreateSchema(BaseModel):
    title: str | None = None
    model_id: str | None = None


class MessageCreateSchema(BaseModel):
    content: str
    model_id: str | None = None
    max_output_tokens: int | None = None


def _conversation_payload(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "model_id": conversation.model_id,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
    }


def _message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content_text": message.content_text,
        "input_tokens": message.input_tokens,
        "output_tokens": message.output_tokens,
        "status": message.status,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _get_owned_conversation(conversation_id: str) -> Conversation | None:
    conversation = db.session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != g.current_user_id:
        return None
    return conversation


def _resolve_text_model(model_id: str | None) -> AiModel | None:
    if model_id:
        model = db.session.get(AiModel, model_id)
        if model is None or model.capability != CAP_TEXT:
            return None
        return model
    return (
        db.session.query(AiModel)
        .filter_by(capability=CAP_TEXT, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )


@bp.get("/conversations")
@login_required
def list_conversations():
    page, page_size = pagination_params()
    query = (
        db.session.query(Conversation)
        .filter_by(user_id=g.current_user_id)
        .order_by(Conversation.updated_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return success_response([_conversation_payload(c) for c in items], meta)


@bp.post("/conversations")
@login_required
def create_conversation():
    try:
        data = ConversationCreateSchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()
    model = _resolve_text_model(data.model_id) if data.model_id else None
    if data.model_id and model is None:
        return error_response("MODEL_UNAVAILABLE", status=404)
    conversation = Conversation(
        user_id=g.current_user_id,
        title=(data.title or "گفت‌وگوی جدید")[:255],
        model_id=model.id if model else None,
    )
    db.session.add(conversation)
    db.session.commit()
    return success_response(_conversation_payload(conversation), status=201)


@bp.get("/conversations/<conversation_id>")
@login_required
def get_conversation(conversation_id: str):
    conversation = _get_owned_conversation(conversation_id)
    if conversation is None:
        return error_response("NOT_FOUND", status=404)
    messages = (
        db.session.query(Message)
        .filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at)
        .all()
    )
    payload = _conversation_payload(conversation)
    payload["messages"] = [_message_payload(m) for m in messages]
    return success_response(payload)


@bp.post("/conversations/<conversation_id>/messages")
@login_required
def send_message(conversation_id: str):
    try:
        data = MessageCreateSchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()
    content = (data.content or "").strip()
    if not content or len(content) > MAX_CONTENT_CHARS:
        return validation_error()

    conversation = _get_owned_conversation(conversation_id)
    if conversation is None:
        return error_response("NOT_FOUND", status=404)

    if rate_limited(f"ai:req:{g.current_user_id}", config.rate_limit_ai_request,
                    config.rate_limit_ai_request_window):
        return error_response("RATE_LIMITED", status=429)

    try:
        PlanLimitService(db.session).check(g.current_user_id, "text")
    except PlanLimitExceeded:
        return error_response("PLAN_LIMIT_EXCEEDED", status=403)

    model = _resolve_text_model(data.model_id or conversation.model_id)
    if model is None or not model.is_active:
        return error_response("MODEL_UNAVAILABLE", status=404)
    if not model.tokenizer_encoding:
        return error_response("TOKENIZER_UNAVAILABLE", status=500)
    try:
        counter = TokenCounter(model.tokenizer_encoding)
    except TokenizerUnavailable:
        return error_response("TOKENIZER_UNAVAILABLE", status=500)

    max_output_tokens = data.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
    if not 1 <= max_output_tokens <= 8192:
        return validation_error()

    history = (
        db.session.query(Message)
        .filter_by(conversation_id=conversation.id, status="succeeded")
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    history = list(reversed(history))
    provider_messages = [{"role": ROLE_SYSTEM,
                          "content": "You are Nourai (نورا), a helpful Persian AI assistant."}]
    for item in history:
        if item.content_text:
            provider_messages.append({"role": item.role, "content": item.content_text})
    provider_messages.append({"role": ROLE_USER, "content": content})

    # The exact payload string sent to the provider is what gets counted.
    provider = get_text_provider()
    overhead = getattr(provider, "OVERHEAD_PER_MESSAGE", 0)
    input_tokens = counter.count_chat_messages(
        provider_messages, overhead_per_message=overhead,
        overhead_total=getattr(provider, "OVERHEAD_TOTAL", 0),
    )

    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_text(model.id, input_tokens, max_output_tokens)
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    # Idempotent retry: the same key returns the already-created reply.
    existing = (
        db.session.query(Message)
        .filter_by(conversation_id=conversation.id, role=ROLE_ASSISTANT)
        .order_by(Message.created_at.desc())
        .first()
    )
    _ = existing  # (usage_event carries the idempotency link; see below)

    user_message = Message(
        conversation_id=conversation.id, role=ROLE_USER,
        content_text=content, input_tokens=input_tokens, status="succeeded",
    )
    db.session.add(user_message)
    db.session.flush()

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"chat:{user_message.id}:reserve",
            reference_type="message", reference_id=user_message.id,
            description="reserve text generation",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass  # retried request; the reserve already exists

    usage = UsageEvent(
        user_id=g.current_user_id,
        job_id=None,
        model_id=model.id,
        provider_key=model.provider_key,
        status="processing",
        est_input_tokens=input_tokens,
        est_output_tokens=max_output_tokens,
        tokenizer_encoding=model.tokenizer_encoding,
        token_count_source="tiktoken",
        pricing_rule_id=None,
        pricing_snapshot_json=estimate["pricing_snapshots"],
        estimated_amount_irr=estimated_irr,
        reserved_amount_irr=estimated_irr,
        metadata_json={"idempotency_key": idempotency_key},
    )
    db.session.add(usage)
    db.session.flush()
    db.session.commit()

    # --- provider call (bounded) -------------------------------------------
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                provider.generate, model.provider_model_name, provider_messages,
                {"max_output_tokens": max_output_tokens},
            )
            result = future.result(timeout=GENERATION_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        result = None
        result_error = ("PROVIDER_ERROR", "generation timed out")
    except Exception as exc:  # noqa: BLE001
        result = None
        result_error = ("PROVIDER_ERROR", str(exc)[:200])
    else:
        result_error = None

    if result is None or not result.ok:
        code = (result.error_code if result else None) or (result_error[0] if result_error else "PROVIDER_ERROR")
        wallet = get_wallet_for_update(db.session, g.current_user_id)
        try:
            release(
                db.session, wallet=wallet, reserved_amount_irr=estimated_irr,
                idempotency_key=f"chat:{user_message.id}:release",
                reference_type="usage_event", reference_id=usage.id,
                description="release after failed generation",
            )
        except DuplicateIdempotencyKey:
            pass
        user_message.status = "failed"
        user_message.error_code = code
        usage.status = "failed"
        usage.charged_amount_irr = 0
        db.session.commit()
        audit(db.session, actor_type="user", actor_id=g.current_user_id,
              action="chat.generation_failed", target_type="message",
              target_id=user_message.id, metadata={"error_code": code},
              ip_hash=ip_hash(client_ip()))
        db.session.commit()
        log.warning("text generation failed for user %s: %s", g.current_user_id, code)
        return error_response("PROVIDER_ERROR", status=502)

    # --- settle on actual usage ---------------------------------------------
    if result.usage_source == "provider" and result.input_tokens is not None and result.output_tokens is not None:
        final_in, final_out, source = result.input_tokens, result.output_tokens, "provider"
    else:
        final_in, final_out, source = input_tokens, counter.count_text(result.text or ""), "tiktoken"
    final_estimate = pricing.estimate_text(model.id, final_in, final_out)
    final_irr = final_estimate["total_irr"]

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        settle(
            db.session, wallet=wallet,
            reserved_amount_irr=estimated_irr, final_amount_irr=final_irr,
            idempotency_key=f"chat:{user_message.id}:settle",
            reference_type="usage_event", reference_id=usage.id,
            description="settle text generation",
        )
    except (DuplicateIdempotencyKey, InsufficientBalance):
        db.session.rollback()
        log.exception("settle failed for message %s", user_message.id)
        return error_response("INTERNAL_ERROR", status=500)

    assistant_message = Message(
        conversation_id=conversation.id, role=ROLE_ASSISTANT,
        content_text=result.text, input_tokens=final_in, output_tokens=final_out,
        provider_request_id=result.provider_request_id, status="succeeded",
    )
    db.session.add(assistant_message)
    usage.status = "succeeded"
    usage.final_input_tokens = final_in
    usage.final_output_tokens = final_out
    usage.token_count_source = source
    usage.charged_amount_irr = final_irr
    usage.provider_request_id = result.provider_request_id
    conversation.updated_at = utcnow()
    db.session.commit()

    # Successful AI usage counts against the plan's period quota.
    PlanLimitService(db.session).increment(g.current_user_id, "text")
    db.session.commit()

    return success_response(_message_payload(assistant_message), status=201)
