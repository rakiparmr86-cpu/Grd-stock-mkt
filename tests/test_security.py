from __future__ import annotations

import time

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("demo12345")
    assert h != "demo12345"
    assert verify_password("demo12345", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip():
    token = create_access_token(42, extra={"role": "admin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"
    assert payload["exp"] > payload["iat"]


def test_access_token_rejects_tampering():
    token = create_access_token(1)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "not-the-secret", algorithms=[settings.algorithm])


def test_expired_token_raises(monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token(7)
    time.sleep(0.01)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
