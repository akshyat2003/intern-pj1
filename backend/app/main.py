from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth import (
    create_access_token,
    generate_otp,
    get_current_user,
    hash_otp,
    hash_password,
    normalize_email,
    send_otp_email,
    verify_password,
)
from .config import get_settings
from .document_store import chunk_text, store
from .file_loader import extract_text
from .llm_client import generate_answer
from .models import (
    AuthResponse,
    ChatHistoryItem,
    ChatRequest,
    ChatResponse,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    SignupResponse,
    SourceChunk,
    SyncProfileRequest,
    UploadResponse,
    UserProfile,
    VerifyOtpRequest,
)

app = FastAPI(title="RAG Chatbot API")

settings = get_settings()
store.configure(settings.database_url, settings.sqlite_path)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.allowed_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def to_user_profile(user: dict) -> UserProfile:
    settings = get_settings()
    return UserProfile(
        id=str(user["id"]),
        first_name=user["first_name"],
        last_name=user["last_name"],
        email=user["email"],
        phone_number=user["phone_number"],
        is_verified=bool(user.get("is_verified", False)),
        tokens_used=int(user.get("tokens_used", 0)),
        token_limit=int(user.get("token_limit", settings.max_user_tokens)),
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "RAG Chatbot API",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "chunks": len(store.chunks),
        "storage": store.storage_backend,
        "smtp_configured": bool(settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_from_email),
        "smtp_host_set": bool(settings.smtp_host),
        "smtp_username_set": bool(settings.smtp_username),
        "smtp_from_set": bool(settings.smtp_from_email),
    }


# -------------------------
# SIGNUP
# -------------------------
@app.post("/auth/signup", response_model=SignupResponse)
def signup(request: SignupRequest) -> SignupResponse:
    settings = get_settings()

    email = normalize_email(str(request.email))
    otp = generate_otp()

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.otp_expiry_minutes
    )

    existing_user = store.get_user_by_email(email)
    if existing_user:
        if not existing_user.get("is_verified", False):
            store.save_otp(email, hash_otp(otp), expires_at.isoformat())
            email_sent = send_otp_email(settings, email, otp)
            if not email_sent:
                if settings.smtp_host:
                    raise HTTPException(status_code=500, detail="Failed to send verification email. Please verify your SMTP settings (host, port, API credentials, verified sender) on Render.")
                else:
                    if settings.env == "development":
                        print(f"\n--- DEV OTP --- {email} | {otp}\n", flush=True)
                    message = "Account already exists but is unverified. Check server logs for your OTP."
            else:
                message = "Account already exists but is unverified. A new OTP has been sent to your email."
            return SignupResponse(message=message, email=email)
        else:
            raise HTTPException(status_code=409, detail="A user with this email already exists.")

    try:
        store.create_user(
            request.first_name.strip(),
            request.last_name.strip(),
            email,
            request.phone_number.strip(),
            hash_password(request.password),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store.save_otp(email, hash_otp(otp), expires_at.isoformat())

    email_sent = send_otp_email(settings, email, otp)

    if not email_sent:
        if settings.smtp_host:
            raise HTTPException(status_code=500, detail="Failed to send verification email. Please verify your SMTP settings (host, port, API credentials, verified sender) on Render.")
        else:
            if settings.env == "development":
                print(f"\n--- DEV OTP --- {email} | {otp}\n", flush=True)
            message = "Signup successful. SMTP is not configured. Check server logs (dev mode)."
    else:
        message = "Signup successful. Check your email for OTP."

    return SignupResponse(message=message, email=email)


# -------------------------
# VERIFY OTP
# -------------------------
@app.post("/auth/verify-otp", response_model=MessageResponse)
def verify_otp(request: VerifyOtpRequest) -> MessageResponse:
    email = normalize_email(str(request.email))
    record = store.get_otp(email)

    if not record:
        raise HTTPException(400, "OTP not found. Please sign up again.")

    expires_at = datetime.fromisoformat(record["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "OTP expired. Please sign up again.")

    # FIX: brute-force protection (assumes store supports this)
    attempts = store.increment_otp_attempts(email)
    if attempts > 5:
        store.delete_otp(email)
        raise HTTPException(429, "Too many OTP attempts. Please sign up again.")

    if record["otp_hash"] != hash_otp(request.otp.strip()):
        raise HTTPException(400, "Invalid OTP.")

    store.verify_user(email)
    store.delete_otp(email)

    return MessageResponse(message="Account verified. You can now log in.")


# -------------------------
# LOGIN
# -------------------------
@app.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    settings = get_settings()
    email = normalize_email(str(request.email))

    user = store.get_user_by_email(email)

    if not user:
        raise HTTPException(401, "Invalid credentials")

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")

    if not user.get("is_verified", False):
        raise HTTPException(403, "Verify your account before logging in.")

    token = create_access_token(settings, str(user["id"]))

    return AuthResponse(access_token=token, user=to_user_profile(user))


# -------------------------
# ME
# -------------------------
@app.get("/auth/me", response_model=UserProfile)
def me(user: dict = Depends(get_current_user)) -> UserProfile:
    return to_user_profile(user)


# -------------------------
# SYNC PROFILE
# -------------------------
@app.post("/auth/sync", response_model=UserProfile)
def sync_profile(
    request: SyncProfileRequest,
    user: dict = Depends(get_current_user),
) -> UserProfile:
    store.update_user_profile(
        uid=user["id"],
        first_name=request.first_name.strip(),
        last_name=request.last_name.strip(),
        phone_number=request.phone_number.strip(),
    )

    updated_user = store.get_user_by_id(user["id"])
    return to_user_profile(updated_user)


# -------------------------
# UPLOAD FILE
# -------------------------
@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> UploadResponse:
    settings = get_settings()
    filename = file.filename or "uploaded-file"

    try:
        text = await extract_text(file)
        chunks = chunk_text(text, filename, settings.chunk_size, settings.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"File error: {exc}") from exc

    if not chunks:
        raise HTTPException(400, "No readable text found.")

    added = store.add_chunks(str(user["id"]), filename, text, chunks)

    return UploadResponse(
        filename=filename,
        chunks_added=added,
        total_chunks=len(store.get_user_chunks(str(user["id"]))),
    )


# -------------------------
# CHAT (RAG)
# -------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
) -> ChatResponse:

    settings = get_settings()
    user_id = str(user["id"])
    question = request.question.strip()

    if not question:
        raise HTTPException(400, "Question is required.")

    user_db = store.get_user_by_id(user_id) or user

    tokens_used = int(user_db.get("tokens_used", 0))
    token_limit = int(user_db.get("token_limit", settings.max_user_tokens))

    if tokens_used >= token_limit:
        raise HTTPException(
            403,
            f"Token limit reached ({token_limit}).",
        )

    store.add_chat_message(user_id, "user", question)

    results = store.search(user_id, question, settings.max_context_chunks)

    if not results:
        answer = "I do not know based on uploaded files."
        store.add_chat_message(user_id, "assistant", answer)

        from .llm_client import estimate_tokens

        p_tokens = estimate_tokens(question)
        c_tokens = estimate_tokens(answer)

        total = p_tokens + c_tokens
        updated_user = store.increment_user_tokens(user_id, total) or user_db

        return ChatResponse(
            answer=answer,
            sources=[],
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=total,
            context_window_limit=settings.model_context_window,
            tokens_used=int(updated_user.get("tokens_used", 0)),
            token_limit=int(updated_user.get("token_limit", settings.max_user_tokens)),
        )

    # FIX: safer prompt injection protection
    context_parts = [
        f"[{i}] FILE: {chunk.filename}\n<<<{chunk.text}>>>"
        for i, (chunk, _) in enumerate(results, start=1)
    ]

    context = "\n\n".join(context_parts)

    try:
        answer, prompt_tokens, completion_tokens = await generate_answer(
            settings, question, context
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc

    total = prompt_tokens + completion_tokens

    updated_user = store.increment_user_tokens(user_id, total) or user_db

    sources = [
        SourceChunk(
            filename=chunk.filename,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            score=round(score, 4),
        )
        for chunk, score in results
    ]

    store.add_chat_message(
        user_id,
        "assistant",
        answer,
        [s.model_dump() for s in sources],
    )

    return ChatResponse(
        answer=answer,
        sources=sources,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total,
        context_window_limit=settings.model_context_window,
        tokens_used=int(updated_user.get("tokens_used", 0)),
        token_limit=int(updated_user.get("token_limit", settings.max_user_tokens)),
    )


# -------------------------
# CHAT HISTORY
# -------------------------
@app.get("/chat/history", response_model=list[ChatHistoryItem])
def chat_history(user: dict = Depends(get_current_user)) -> list[ChatHistoryItem]:
    rows = store.get_chat_history(str(user["id"]))
    return [ChatHistoryItem(**row) for row in rows]