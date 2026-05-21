from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ai_provider: str = Field(default="groq", validation_alias="AI_PROVIDER")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="ALLOWED_ORIGINS"
    )
    allowed_origin_regex: str = Field(
        default=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        validation_alias="ALLOWED_ORIGIN_REGEX",
    )

    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.1-8b-instant", validation_alias="GROQ_MODEL")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", validation_alias="GROQ_BASE_URL")

    nvidia_api_key: str = Field(default="", validation_alias="NVIDIA_API_KEY")
    nvidia_model: str = Field(default="meta/llama-3.1-8b-instruct", validation_alias="NVIDIA_MODEL")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", validation_alias="NVIDIA_BASE_URL")

    max_context_chunks: int = Field(default=5, validation_alias="MAX_CONTEXT_CHUNKS")
    chunk_size: int = Field(default=900, validation_alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, validation_alias="CHUNK_OVERLAP")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    sqlite_path: str = Field(default="data/documents.db", validation_alias="SQLITE_PATH")

    @property
    def provider_api_key(self) -> str:
        api_key = self.groq_api_key if self.normalized_provider == "groq" else self.nvidia_api_key
        return api_key.strip()

    @property
    def provider_model(self) -> str:
        return self.groq_model if self.normalized_provider == "groq" else self.nvidia_model

    @property
    def provider_base_url(self) -> str:
        return self.groq_base_url if self.normalized_provider == "groq" else self.nvidia_base_url

    @property
    def normalized_provider(self) -> str:
        return self.ai_provider.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
