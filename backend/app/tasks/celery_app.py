"""Celery application instance."""
from app.extensions import make_celery

celery = make_celery()
