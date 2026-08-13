"""UTC-only helpers for every public time boundary."""

from __future__ import annotations

from datetime import UTC, datetime

from .errors import ContractError


def ensure_utc(value: datetime, *, field: str = "time") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def parse_utc(value: str | datetime, *, field: str = "time") -> datetime:
    if isinstance(value, datetime):
        return ensure_utc(value, field=field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be an ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{field} is not valid ISO-8601: {value!r}") from exc
    return ensure_utc(parsed, field=field)


def isoformat_utc(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")
