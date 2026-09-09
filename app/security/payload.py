from __future__ import annotations

import hmac
import hashlib
import json
import secrets
import time
from typing import Any

from app.config import Settings


class PayloadError(ValueError):
    pass


def sign_dict(settings: Settings, data: dict[str, Any], ttl_sec: int) -> str:
    payload = {
        **data,
        "exp": int(time.time()) + ttl_sec,
        "n": secrets.token_urlsafe(12),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{digest}.{raw}"


def verify_signed(settings: Settings, token: str) -> dict[str, Any]:
    try:
        digest, raw = token.split(".", 1)
    except ValueError as exc:
        raise PayloadError("malformed") from exc
    expected = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise PayloadError("bad signature")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadError("bad json") from exc
    if int(data.get("exp", 0)) < int(time.time()):
        raise PayloadError("expired")
    return data


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
