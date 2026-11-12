"""Assemble route blueprints and register shared API error handlers."""

from .admin import admin_blueprint
from .common import register_api_error_handlers
from .pages import pages_blueprint
from .public import public_blueprint, shortlink_redirect_blueprint


register_api_error_handlers(admin_blueprint)
register_api_error_handlers(public_blueprint)
register_api_error_handlers(shortlink_redirect_blueprint)


__all__ = [
    "admin_blueprint",
    "pages_blueprint",
    "public_blueprint",
    "shortlink_redirect_blueprint",
]
