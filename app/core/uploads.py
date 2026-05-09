import hashlib
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.core.file_utils import FileValidationError, validate_file_size
from app.core.storage import storage_manager


UPLOAD_CHUNK_SIZE = 1024 * 1024


async def save_upload_to_temp(file: UploadFile) -> tuple[Path, str, int]:
    temp_path = storage_manager.create_temp_upload_path()
    digest = hashlib.md5()
    file_size = 0

    try:
        with temp_path.open("wb") as output:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > settings.max_upload_size_bytes:
                    raise FileValidationError("file_too_large", "file is too large")
                digest.update(chunk)
                output.write(chunk)

        validate_file_size(file_size, settings.max_upload_size_bytes)
        return temp_path, digest.hexdigest(), file_size
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
