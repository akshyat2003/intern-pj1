from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import random

import jwt
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .document_store import store


security = HTTPBearer()


def normalize_email(email: str) -> str:
    return email.strip().lower()


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


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def create_access_token(settings: Settings, user_id: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_token_minutes)
    payload = {"sub": user_id, "exp": expires_at}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> str:
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user_id


def send_otp_sms(settings: Settings, phone_number: str, otp: str) -> bool:
    if not settings.msg91_authkey or not settings.msg91_template_id:
        return False

    cleaned_phone = "".join(c for c in phone_number if c.isdigit())
    if not cleaned_phone:
        return False

    url = "https://control.msg91.com/api/v5/otp"
    params = {
        "template_id": settings.msg91_template_id,
        "mobile": cleaned_phone,
        "authkey": settings.msg91_authkey,
        "otp": otp
    }

    try:
        response = httpx.post(url, params=params, json={})
        if response.status_code == 200:
            resp_data = response.json()
            if resp_data.get("type") == "success":
                return True
        return False
    except Exception as e:
        print(f"Failed to send MSG91 OTP: {e}")
        return False



def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    user_id = decode_access_token(settings, credentials.credentials)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="Verify your account before using the app.")
    return user
