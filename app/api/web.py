from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


WEB_STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

router = APIRouter(tags=["web"])


@router.get("/web", include_in_schema=False)
@router.get("/web/", include_in_schema=False)
def web_index() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "index.html")
