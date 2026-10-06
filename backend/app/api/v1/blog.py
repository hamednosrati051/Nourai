"""Public blog: published posts only."""
from __future__ import annotations

from flask import Blueprint, Response, request

from app.api.deps import error_response, success_response
from app.extensions import db
from app.models import BlogPost
from app.services.storage import storage

bp = Blueprint("blog", __name__)


def _public_payload(p: BlogPost) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "cover_image_url": p.cover_image_url,
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


@bp.get("/blog/cover")
def get_blog_cover():
    """Serve a blog cover image from storage."""
    key = request.args.get("key", "")
    if not key.startswith("blog/covers/") or ".." in key:
        return error_response("NOT_FOUND", status=404)
    try:
        data = storage.get_bytes(key)
    except Exception:
        return error_response("NOT_FOUND", status=404)
    ext = key.rsplit(".", 1)[-1].lower()
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
             "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    return Response(data, mimetype=ctype, headers={"Cache-Control": "public, max-age=86400"})


@bp.get("/blog/image")
def get_blog_image():
    """Serve an inline blog body image from storage."""
    key = request.args.get("key", "")
    if not key.startswith("blog/images/") or ".." in key:
        return error_response("NOT_FOUND", status=404)
    try:
        data = storage.get_bytes(key)
    except Exception:
        return error_response("NOT_FOUND", status=404)
    ext = key.rsplit(".", 1)[-1].lower()
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
             "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    return Response(data, mimetype=ctype, headers={"Cache-Control": "public, max-age=86400"})
