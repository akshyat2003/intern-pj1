from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import random

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .document_store import store

security = HTTPBearer()

MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"


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


def send_otp_sms(settings: Settings, phone: str, otp: str) -> bool:
    """Send OTP via MSG91 SMS. Returns True on success, False if not configured."""
    if not settings.msg91_authkey or not settings.msg91_template_id:
        print("[MSG91] Not configured — printing OTP to logs (dev mode)", flush=True)
        print(f"[DEV OTP] Phone: {phone} | OTP: {otp}", flush=True)
        return False

    mobile = normalize_phone(phone)

    try:
        response = httpx.post(
            MSG91_OTP_URL,
            headers={
                "authkey": settings.msg91_authkey,
                "Content-Type": "application/json",
            },
            json={
                "otp": otp,
                "mobile": mobile,
                "template_id": settings.msg91_template_id,
            },
            timeout=10,
        )
        data = response.json()
        if data.get("type") == "success":
            print(f"[MSG91] OTP sent to {mobile}", flush=True)
            return True
        else:
            print(f"[MSG91] Failed: {data}", flush=True)
            return False
    except Exception as e:
        print(f"[MSG91 ERROR] {repr(e)}", flush=True)
        return False


def safe_send_otp_sms(settings: Settings, phone: str, otp: str) -> None:
    """Wrapper for BackgroundTasks — never raises, always logs."""
    try:
        send_otp_sms(settings, phone, otp)
    except Exception as e:
        print(f"[BACKGROUND MSG91 ERROR] {repr(e)}", flush=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    user_id = decode_access_token(settings, credentials.credentials)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if not user.get("is_verified"):
        raise HTTPException(status_code=403, detail="Verify your account before using the app.")
    return user