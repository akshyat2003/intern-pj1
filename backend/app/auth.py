from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .document_store import store

security = HTTPBearer()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Strip leading + and spaces. MSG91 expects digits only with country code."""
    return phone.strip().lstrip("+").replace(" ", "").replace("-", "")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _scheme, iterations, salt_hex, digest_hex = stored_hash.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


def create_access_token(settings: Settings, user_id: str, session_token: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_token_minutes)
    payload = {"sub": user_id, "session_token": session_token, "exp": expires_at}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> tuple[str, str]:
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc

    user_id = payload.get("sub")
    session_token = payload.get("session_token")
    if not isinstance(user_id, str) or not user_id or not session_token:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user_id, session_token


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    user_id, session_token = decode_access_token(settings, credentials.credentials)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
        
    active_session = user.get("active_session_token")
    if active_session and active_session != session_token:
        raise HTTPException(status_code=401, detail="Logged in from another device. Please log in again.")
        
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="Verify your account before using the app.")
    return user