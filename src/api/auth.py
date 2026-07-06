"""Аутентификация Telegram Mini App: HMAC-валидация initData + allowlist."""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request

from ..utils.config import ALLOWED_USER_IDS, AUTH_DISABLED, BOT_TOKEN


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """HMAC-SHA256 проверка подписи initData. None = невалидно."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    return parsed


async def require_tg_auth(request: Request) -> dict:
    """FastAPI dependency: валидирует заголовок Telegram-Init-Data."""
    if AUTH_DISABLED:
        return {"user": json.dumps({"id": 0, "dev": True})}
    init_data = request.headers.get("Telegram-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram-Init-Data header")
    parsed = verify_init_data(init_data, BOT_TOKEN)
    if parsed is None:
        raise HTTPException(status_code=403, detail="Invalid Telegram initData")
    if ALLOWED_USER_IDS:
        try:
            user_id = json.loads(parsed.get("user", "{}")).get("id")
        except json.JSONDecodeError:
            user_id = None
        if user_id not in ALLOWED_USER_IDS:
            raise HTTPException(status_code=403, detail="User not allowed")
    return parsed
