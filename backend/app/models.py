from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone_number: str = Field(min_length=6, max_length=30)
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter (A-Z).")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter (a-z).")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number (0-9).")
        special_characters = set("@#$%" + "&*-_+=!?^~.,;/\\|()[]{}':\"`<>")
        if not any(c in special_characters for c in v):
            raise ValueError("Password must contain at least one special character (@, #, $, %, &, *, etc.).")
        return v


class SignupResponse(BaseModel):
    message: str


class LoginRequest(BaseModel):
    identifier: str
    password: str


class MessageResponse(BaseModel):
    message: str


class SyncProfileRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone_number: str = Field(min_length=6, max_length=30)


# Must be defined BEFORE AuthResponse which references it
class UserProfile(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    is_verified: bool
    tokens_used: int = 0
    token_limit: int = 50000


class AuthResponse(BaseModel):
    access_token: str
    user: UserProfile


class ChatRequest(BaseModel):
    question: str


class SourceChunk(BaseModel):
    filename: str
    chunk_id: int
    text: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    context_window_limit: int
    tokens_used: int
    token_limit: int


class ChatHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    sources: list[SourceChunk] | None = None
    created_at: str


class UploadResponse(BaseModel):
    filename: str
    chunks_added: int
    total_chunks: int
