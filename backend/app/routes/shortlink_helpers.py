"""Validation and serialization helpers for public shortlinks."""

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from flask import current_app
from itsdangerous import URLSafeTimedSerializer

from ..models import ShortLink


SHORTLINK_ALIAS_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,62}\Z")


def valid_shortlink_url(value: object) -> bool:
    """Check that a destination is a credential-free HTTP or HTTPS URL."""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 2048:
        return False
    try:
        parsed = urlsplit(value.strip())
        parsed.port
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def parse_shortlink_expiry(value: object) -> datetime | None:
    """Parse an optional ISO timestamp and normalize it to naive UTC."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Masa berlaku harus berupa waktu ISO 8601.")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        expiry = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("Masa berlaku harus berupa waktu ISO 8601.") from error
    if expiry.tzinfo is None:
        raise ValueError("Masa berlaku harus menyertakan zona waktu.")
    expiry_utc = expiry.astimezone(timezone.utc).replace(tzinfo=None)
    if expiry_utc <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError("Masa berlaku harus berada di masa depan.")
    return expiry_utc


def shortlink_form_serializer() -> URLSafeTimedSerializer:
    """Create the signer used for shortlink form anti-bot tokens."""
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="ppm-tools-shortlink-form",
    )


def shortlink_json(link: ShortLink, click_count: int | None = None) -> dict:
    """Serialize a shortlink using UTC timestamps and a relative public URL."""
    result = {
        "id": link.id,
        "alias": link.alias,
        "title": link.title,
        "target_url": link.target_url,
        "is_active": link.is_active,
        "expires_at": link.expires_at.isoformat(sep=" ") if link.expires_at else None,
        "created_at": link.created_at.isoformat(sep=" "),
        "updated_at": link.updated_at.isoformat(sep=" "),
        "short_url": f"/s/{link.alias}",
    }
    if click_count is not None:
        result["click_count"] = click_count
    return result
