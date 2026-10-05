"""User usage history with filters (capability, model, date range)."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, g, request

from app.api.deps import login_required, paginate_query, paginated_response, pagination_params, success_response
from app.extensions import db
from app.models import AiModel, UsageEvent

bp = Blueprint("usage", __name__)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/usage")
@login_required
def list_usage():
    capability = request.args.get("capability")
    model_id = request.args.get("model_id")
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))

    query = db.session.query(UsageEvent).filter_by(user_id=g.current_user_id)
    if model_id:
        query = query.filter_by(model_id=model_id)
    if date_from:
        query = query.filter(UsageEvent.created_at >= date_from)
    if date_to:
        query = query.filter(UsageEvent.created_at <= date_to)

    page, page_size = pagination_params()
    if capability:
        # Join jobs to filter by capability.
        from app.models import GenerationJob

        query = query.join(GenerationJob, UsageEvent.job_id == GenerationJob.id).filter(
            GenerationJob.capability == capability
        )
    query = query.order_by(UsageEvent.created_at.desc())
    items, meta = paginate_query(query, page, page_size)

    model_names = {
        m.id: m.display_name
        for m in db.session.query(AiModel).filter(
            AiModel.id.in_({i.model_id for i in items if i.model_id})
        ).all()
    }
    model_capabilities = {
        m.id: m.capability
        for m in db.session.query(AiModel).filter(
            AiModel.id.in_({i.model_id for i in items if i.model_id})
        ).all()
    }

    def _service_and_usage(e):
        cap = model_capabilities.get(e.model_id, "")
        if cap in ("generate_image", "edit_image", "image"):
            service = "image"
            amount = e.image_count
            unit = "تصویر"
        elif cap in ("speech_to_text", "text_to_speech"):
            service = "audio"
            amount = e.audio_seconds
            unit = "ثانیه"
        else:
            service = "text"
            amount = (e.final_input_tokens or 0) + (e.final_output_tokens or 0) or None
            unit = "توکن"
        return service, amount, unit

    return paginated_response(
        [
            {
                "id": e.id,
                "model_id": e.model_id,
                "model_name": model_names.get(e.model_id),
                "service": _service_and_usage(e)[0],
                "status": e.status,
                "est_input_tokens": e.est_input_tokens,
                "final_input_tokens": e.final_input_tokens,
                "est_output_tokens": e.est_output_tokens,
                "final_output_tokens": e.final_output_tokens,
                "audio_seconds": e.audio_seconds,
                "image_count": e.image_count,
                "usage_amount": _service_and_usage(e)[1],
                "usage_unit": _service_and_usage(e)[2],
                "charged_amount_irr": e.charged_amount_irr,
                "token_count_source": e.token_count_source,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        page,
        page_size,
        meta["total"],
    )
