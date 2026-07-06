import hashlib
import hmac
import json
from urllib.parse import urlencode

from src.api.auth import verify_init_data

TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id: int, token: str = TOKEN, tamper: bool = False) -> str:
    params = {
        "auth_date": "1700000000",
        "user": json.dumps({"id": user_id, "first_name": "Max"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if tamper:
        params["user"] = json.dumps({"id": 999, "first_name": "Evil"})
    return urlencode({**params, "hash": h})


def test_valid_signature():
    parsed = verify_init_data(make_init_data(42), TOKEN)
    assert parsed is not None
    assert json.loads(parsed["user"])["id"] == 42


def test_tampered_payload_rejected():
    assert verify_init_data(make_init_data(42, tamper=True), TOKEN) is None


def test_wrong_token_rejected():
    assert verify_init_data(make_init_data(42, token="999:OTHER"), TOKEN) is None


def test_garbage_rejected():
    assert verify_init_data("hash=zzz", TOKEN) is None
    assert verify_init_data("", TOKEN) is None
