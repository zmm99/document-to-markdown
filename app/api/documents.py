from fastapi import APIRouter, HTTPException, status

from app.core.file_utils import FileValidationError, validate_file_id
from app.core.storage import storage_manager
from app.db.database import get_connection
from app.db.repository import (
    delete_parse_cache_records,
    get_document,
    list_parse_output_dirs,
)


router = APIRouter(prefix="/documents", tags=["documents"])


def raise_api_error(status_code: int, error_code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "status": "failed",
            "error_code": error_code,
            "message": message,
        },
    )


@router.delete("/{file_id}/cache")
def delete_document_cache(file_id: str) -> dict[str, int | str]:
    try:
        document_id = validate_file_id(file_id)
    except FileValidationError as exc:
        raise_api_error(status.HTTP_400_BAD_REQUEST, exc.error_code, exc.message)

    with get_connection() as conn:
        document = get_document(conn, document_id)
        if document is None:
            raise_api_error(
                status.HTTP_404_NOT_FOUND,
                "document_not_found",
                "document not found",
            )

        output_dirs = list_parse_output_dirs(conn, document_id)
        deleted_output_dirs = 0
        for output_dir in output_dirs:
            if storage_manager.delete_output_dir(output_dir):
                deleted_output_dirs += 1

        deleted_counts = delete_parse_cache_records(conn, document_id)
        conn.commit()

    return {
        "file_id": document_id,
        "status": "success",
        "deleted_parse_records": deleted_counts["parse_records"],
        "deleted_assets": deleted_counts["assets"],
        "deleted_output_dirs": deleted_output_dirs,
    }
