from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import jwt
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


def send_otp_email(settings: Settings, email: str, otp: str) -> bool:
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password or not settings.smtp_from_email:
        print("[SMTP] Not configured, skipping email", flush=True)
        print(f"[DEV OTP] {email} -> {otp}", flush=True)
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from_email
        msg["To"] = email
        msg["Subject"] = "Your Verification OTP"

        body = (
            f"Hello,\n\n"
            f"Your verification OTP code is: {otp}\n\n"
            f"This OTP is valid for {settings.otp_expiry_minutes} minutes."
        )
        msg.attach(MIMEText(body, "plain"))

        print("[SMTP] Connecting...", flush=True)

        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
            server.ehlo()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            server.ehlo()
            print("[SMTP] Starting TLS...", flush=True)
            server.starttls()
            server.ehlo()

        print("[SMTP] Logging in...", flush=True)
        server.login(settings.smtp_username, settings.smtp_password)

        print("[SMTP] Sending email...", flush=True)
        server.send_message(msg)
        server.quit()

        print("[SMTP] Success", flush=True)
        return True

    except Exception as e:
        print(f"[SMTP ERROR SAFE] {repr(e)}", flush=True)
        return False


def safe_send_otp(settings: Settings, email: str, otp: str) -> None:
    """Wrapper for use with BackgroundTasks — never raises, always logs."""
    try:
        send_otp_email(settings, email, otp)
    except Exception as e:
        print(f"[BACKGROUND SMTP ERROR] {repr(e)}", flush=True)


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