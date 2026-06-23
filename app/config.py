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
    docling_artifacts_path: Path | None = None
    rapidocr_model_path: Path | None = None
    ocr_default_mode: str = "auto"
    layout_engine_default: str = "auto"
    ppstructure_api_url: str | None = None
    ppstructure_timeout_seconds: int = 300
    ppstructure_full_parse_timeout_seconds: int = 120
    ppstructure_page_retry_timeout_seconds: int = 60
    ppstructure_page_retry_min_pages: int = 50
    ppstructure_preprocess_retry_enabled: bool = True
    ppstructure_preprocess_threshold: int = 185
    ppstructure_page_image_fallback_enabled: bool = True
    ppstructure_page_image_fallback_max_side: int = 1800
    ppstructure_render_scale: float = 1.5
    ppstructure_use_table_recognition: bool = True
    ppstructure_use_seal_recognition: bool = True
    convert_timeout_seconds: int = 300
    max_concurrent_conversions: int = 2
    admin_username: str = "admin"
    admin_password: str = "admin123"
    session_secret: str = "change-me"
    session_expire_hours: int = 12
    task_worker_count: int = 1

    @field_validator("docling_artifacts_path", mode="before")
    @classmethod
    def validate_docling_artifacts_path(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @field_validator("rapidocr_model_path", mode="before")
    @classmethod
    def validate_rapidocr_model_path(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @field_validator("ppstructure_api_url", mode="before")
    @classmethod
    def validate_ppstructure_api_url(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @field_validator("ocr_default_mode")
    @classmethod
    def validate_ocr_default_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"off", "auto", "full"}:
            raise ValueError("ocr_default_mode must be one of off, auto, full")
        return normalized

    @field_validator("layout_engine_default")
    @classmethod
    def validate_layout_engine_default(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"docling", "ppstructure", "auto"}:
            raise ValueError("layout_engine_default must be one of docling, ppstructure, auto")
        return normalized

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

    @field_validator("convert_timeout_seconds")
    @classmethod
    def validate_convert_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("convert_timeout_seconds must be greater than 0")
        return value

    @field_validator("ppstructure_timeout_seconds")
    @classmethod
    def validate_ppstructure_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ppstructure_timeout_seconds must be greater than 0")
        return value

    @field_validator("ppstructure_full_parse_timeout_seconds")
    @classmethod
    def validate_ppstructure_full_parse_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ppstructure_full_parse_timeout_seconds must be greater than 0")
        return value

    @field_validator("ppstructure_page_retry_timeout_seconds")
    @classmethod
    def validate_ppstructure_page_retry_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ppstructure_page_retry_timeout_seconds must be greater than 0")
        return value

    @field_validator("ppstructure_page_retry_min_pages")
    @classmethod
    def validate_ppstructure_page_retry_min_pages(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ppstructure_page_retry_min_pages must be greater than 0")
        return value

    @field_validator("ppstructure_preprocess_threshold")
    @classmethod
    def validate_ppstructure_preprocess_threshold(cls, value: int) -> int:
        if value <= 0 or value >= 255:
            raise ValueError("ppstructure_preprocess_threshold must be between 1 and 254")
        return value

    @field_validator("ppstructure_page_image_fallback_max_side")
    @classmethod
    def validate_ppstructure_page_image_fallback_max_side(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ppstructure_page_image_fallback_max_side must be greater than 0")
        return value

    @field_validator("ppstructure_render_scale")
    @classmethod
    def validate_ppstructure_render_scale(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ppstructure_render_scale must be greater than 0")
        return value

    @field_validator("max_concurrent_conversions")
    @classmethod
    def validate_max_concurrent_conversions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_concurrent_conversions must be greater than 0")
        return value

    @field_validator("session_expire_hours")
    @classmethod
    def validate_session_expire_hours(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("session_expire_hours must be greater than 0")
        return value

    @field_validator("task_worker_count")
    @classmethod
    def validate_task_worker_count(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("task_worker_count must be greater than 0")
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
