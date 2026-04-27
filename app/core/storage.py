import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.file_utils import (
    build_file_id,
    compute_md5_from_bytes,
    validate_file_size,
    validate_filename_and_format,
)


@dataclass(frozen=True)
class StoredUpload:
    file_id: str
    md5: str
    original_filename: str
    extension: str
    file_format: str
    file_size: int
    storage_date: str
    upload_path: Path
    output_dir: Path

    @property
    def assets_dir(self) -> Path:
        return self.output_dir / "assets"


class StorageManager:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    def get_storage_date(self, now: datetime | None = None) -> str:
        current = now or datetime.now()
        return current.strftime("%Y%m%d")

    def save_upload_bytes(
        self,
        content: bytes,
        filename: str | None,
        now: datetime | None = None,
    ) -> StoredUpload:
        original_filename, extension, file_format = validate_filename_and_format(filename)
        validate_file_size(len(content), settings.max_upload_size_bytes)

        md5_value = compute_md5_from_bytes(content)
        file_id = build_file_id(md5_value)
        storage_date = self.get_storage_date(now)

        upload_dir = self.uploads_dir / storage_date
        output_dir = self.outputs_dir / storage_date / file_id
        upload_path = upload_dir / f"{file_id}{extension}"

        upload_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "assets").mkdir(parents=True, exist_ok=True)

        if not upload_path.exists():
            upload_path.write_bytes(content)

        return StoredUpload(
            file_id=file_id,
            md5=md5_value,
            original_filename=original_filename,
            extension=extension,
            file_format=file_format,
            file_size=len(content),
            storage_date=storage_date,
            upload_path=upload_path,
            output_dir=output_dir,
        )

    def relative_to_data_dir(self, path: Path) -> str:
        return path.resolve().relative_to(self.data_dir.resolve()).as_posix()

    def resolve_data_path(self, relative_path: str) -> Path:
        resolved = (self.data_dir / relative_path).resolve()
        data_root = self.data_dir.resolve()
        if data_root != resolved and data_root not in resolved.parents:
            raise ValueError("path is outside data dir")
        return resolved

    def delete_output_dir(self, relative_path: str) -> bool:
        path = self.resolve_data_path(relative_path)
        outputs_root = self.outputs_dir.resolve()
        if outputs_root != path and outputs_root not in path.parents:
            raise ValueError("path is outside outputs dir")
        if not path.exists():
            return False
        if not path.is_dir():
            raise ValueError("output path is not a directory")
        shutil.rmtree(path)
        return True


storage_manager = StorageManager()
