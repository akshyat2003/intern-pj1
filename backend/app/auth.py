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
import httpx

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
        print(f"[MOCK EMAIL] To: {email} | OTP: {otp}")
        return False

    try:
        # Check if using Brevo (Sendinblue) and route via HTTPS REST API
        # This completely bypasses Render free-tier outbound SMTP port restrictions.
        if "brevo.com" in settings.smtp_host or "sendinblue.com" in settings.smtp_host:
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": settings.smtp_password,
                "content-type": "application/json"
            }
            payload = {
                "sender": {"email": settings.smtp_from_email},
                "to": [{"email": email}],
                "subject": "Your Verification OTP",
                "textContent": f"Hello,\n\nYour verification OTP code is: {otp}\n\nThis OTP is valid for {settings.otp_expiry_minutes} minutes."
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code in (200, 201, 202):
                    print("OTP sent successfully via Brevo HTTP API.")
                    return True
                else:
                    print(f"Brevo HTTP API failed: {resp.status_code} - {resp.text}. Falling back to standard SMTP...")

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from_email
        msg["To"] = email
        msg["Subject"] = "Your Verification OTP"

        body = f"Hello,\n\nYour verification OTP code is: {otp}\n\nThis OTP is valid for {settings.otp_expiry_minutes} minutes."
        msg.attach(MIMEText(body, "plain"))

        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
            server.ehlo()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


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
