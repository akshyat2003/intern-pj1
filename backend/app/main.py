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
    return UserProfile(
        id=str(user["id"]),
        first_name=user["first_name"],
        last_name=user["last_name"],
        email=user["email"],
        phone_number=user["phone_number"],
        is_verified=bool(user["is_verified"]),
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "RAG Chatbot API",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str | int]:
    return {"status": "ok", "chunks": len(store.chunks), "storage": store.storage_backend}


@app.post("/auth/signup", response_model=SignupResponse)
def signup(request: SignupRequest) -> SignupResponse:
    settings = get_settings()
    email = normalize_email(str(request.email))
    otp = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)

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
    return SignupResponse(
        message="Signup successful. Check your email for the OTP." if email_sent else "Signup successful. SMTP is not configured, so use the dev OTP.",
        email=email,
        dev_otp=None if email_sent else otp,
    )


@app.post("/auth/verify-otp", response_model=MessageResponse)
def verify_otp(request: VerifyOtpRequest) -> MessageResponse:
    email = normalize_email(str(request.email))
    record = store.get_otp(email)
    if not record:
        raise HTTPException(status_code=400, detail="OTP not found. Please sign up again.")

    expires_at = datetime.fromisoformat(record["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired. Please sign up again.")

    if record["otp_hash"] != hash_otp(request.otp.strip()):
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    store.verify_user(email)
    store.delete_otp(email)
    return MessageResponse(message="Email verified. You can now log in.")


@app.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest) -> AuthResponse:
    settings = get_settings()
    email = normalize_email(str(request.email))
    user = store.get_user_by_email(email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="Verify your email before logging in.")

    token = create_access_token(settings, str(user["id"]))
    return AuthResponse(access_token=token, user=to_user_profile(user))


@app.get("/auth/me", response_model=UserProfile)
def me(user: dict = Depends(get_current_user)) -> UserProfile:
    return to_user_profile(user)


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> UploadResponse:
    settings = get_settings()
    filename = file.filename or "uploaded-file"

    try:
        text = await extract_text(file)
        chunks = chunk_text(text, filename, settings.chunk_size, settings.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}") from exc

    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text was found in this file.")

    added = store.add_chunks(str(user["id"]), filename, text, chunks)
    user_chunk_count = len([chunk for chunk in store.chunks if chunk.user_id == str(user["id"])])
    return UploadResponse(filename=filename, chunks_added=added, total_chunks=user_chunk_count)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)) -> ChatResponse:
    settings = get_settings()
    user_id = str(user["id"])
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    store.add_chat_message(user_id, "user", question)
    results = store.search(user_id, question, settings.max_context_chunks)
    if not results:
        answer = "I do not know based on the uploaded files. Upload a relevant document first."
        store.add_chat_message(user_id, "assistant", answer)
        return ChatResponse(answer=answer, sources=[])

    context_parts = [
        f"[{index}] Source: {chunk.filename}, chunk {chunk.chunk_id}\n{chunk.text}"
        for index, (chunk, _score) in enumerate(results, start=1)
    ]
    context = "\n\n".join(context_parts)

    try:
        answer = await generate_answer(settings, question, context)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sources = [
        SourceChunk(filename=chunk.filename, chunk_id=chunk.chunk_id, text=chunk.text, score=round(score, 4))
        for chunk, score in results
    ]
    source_dicts = [source.model_dump() for source in sources]
    store.add_chat_message(user_id, "assistant", answer, source_dicts)
    return ChatResponse(answer=answer, sources=sources)


@app.get("/chat/history", response_model=list[ChatHistoryItem])
def chat_history(user: dict = Depends(get_current_user)) -> list[ChatHistoryItem]:
    rows = store.get_chat_history(str(user["id"]))
    return [ChatHistoryItem(**row) for row in rows]
