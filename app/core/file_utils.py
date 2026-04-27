import hashlib
import re
from pathlib import Path
from typing import BinaryIO


SUPPORTED_FILE_FORMATS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}

MD5_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class FileValidationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def normalize_filename(filename: str | None) -> str:
    if filename is None:
        raise FileValidationError("empty_filename", "filename is required")

    normalized = Path(filename).name.strip()
    if not normalized:
        raise FileValidationError("empty_filename", "filename is required")

    return normalized


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def get_file_format(filename: str) -> str:
    extension = get_extension(filename)
    file_format = SUPPORTED_FILE_FORMATS.get(extension)
    if file_format is None:
        raise FileValidationError(
            "unsupported_file_format",
            "unsupported file format",
        )
    return file_format


def validate_filename_and_format(filename: str | None) -> tuple[str, str, str]:
    normalized = normalize_filename(filename)
    extension = get_extension(normalized)
    file_format = get_file_format(normalized)
    return normalized, extension, file_format


def validate_file_size(file_size: int, max_size_bytes: int) -> None:
    if file_size <= 0:
        raise FileValidationError("empty_file", "file is empty")
    if file_size > max_size_bytes:
        raise FileValidationError("file_too_large", "file is too large")


def build_file_id(md5_value: str) -> str:
    file_id = md5_value.replace("-", "").lower()
    if not MD5_PATTERN.fullmatch(file_id):
        raise FileValidationError("invalid_file_id", "file_id must be a md5 value")
    return file_id


def compute_md5_from_bytes(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def compute_md5_from_path(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_md5_from_stream(stream: BinaryIO) -> str:
    digest = hashlib.md5()
    stream.seek(0)
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def validate_file_id(file_id: str) -> str:
    normalized = file_id.replace("-", "").lower()
    if not MD5_PATTERN.fullmatch(normalized):
        raise FileValidationError("invalid_file_id", "file_id must be a md5 value")
    return normalized


def validate_asset_name(asset_name: str) -> str:
    if not asset_name:
        raise FileValidationError("asset_not_found", "asset name is required")

    if asset_name in {".", ".."}:
        raise FileValidationError("asset_not_found", "invalid asset name")

    if Path(asset_name).name != asset_name or "/" in asset_name or "\\" in asset_name:
        raise FileValidationError("asset_not_found", "invalid asset name")

    return asset_name
