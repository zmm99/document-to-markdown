from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "DocumentToMarkdown"
    data_dir: Path = Path("./data")
    max_upload_size_mb: int = 100
    api_prefix: str = "/api"

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith("/"):
            value = f"/{value}"
        return value or "/api"

    @field_validator("max_upload_size_mb")
    @classmethod
    def validate_max_upload_size_mb(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_upload_size_mb must be greater than 0")
        return value

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / "document_to_markdown.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
