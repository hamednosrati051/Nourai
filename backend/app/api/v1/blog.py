"""Public blog: published posts only."""
from __future__ import annotations

from flask import Blueprint

from app.api.deps import error_response, success_response
from app.extensions import db
from app.models import BlogPost

bp = Blueprint("blog", __name__)


def _public_payload(p: BlogPost) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "content": p.content_json or [],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@bp.get("/blog")
def list_blog():
    posts = (
        db.session.query(BlogPost)
        .filter_by(is_published=True)
        .order_by(BlogPost.created_at.desc())
        .all()
    )
    return success_response([_public_payload(p) for p in posts])


@bp.get("/blog/<slug>")
def get_blog_post(slug: str):
    post = (
        db.session.query(BlogPost)
        .filter_by(slug=slug, is_published=True)
        .first()
    )
    if post is None:
        return error_response("NOT_FOUND", status=404)
    return success_response(_public_payload(post))
