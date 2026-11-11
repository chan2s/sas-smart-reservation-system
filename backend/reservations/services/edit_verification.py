"""Helpers for encrypted pending edits and their email verification codes."""

import base64
import hashlib
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password


def _fernet():
    key = hashlib.sha256(
        f"{settings.SECRET_KEY}:reservation-edit-pending-v1".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_payload(payload: dict) -> str:
    return _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decrypt_payload(value: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ValueError("This edit verification session is no longer valid.") from exc


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return make_password(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    return check_password(otp, otp_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
