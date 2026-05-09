from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.tasks import router as tasks_router
from app.api.web import WEB_STATIC_DIR, router as web_router
from app.config import settings
from app.core.response_text import api_error_detail, status_text
from app.core.task_queue import task_queue
from app.db.database import init_db


REQUEST_SIZE_OVERHEAD_BYTES = 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    await task_queue.start()
    yield
    await task_queue.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(tasks_router, prefix=settings.api_prefix)
    app.include_router(web_router)
    app.mount("/web/static", StaticFiles(directory=WEB_STATIC_DIR), name="web-static")

    @app.middleware("http")
    async def upload_size_guard(request: Request, call_next):
        guarded_paths = {
            f"{settings.api_prefix}/documents/convert",
            f"{settings.api_prefix}/tasks/convert",
        }
        if request.method == "POST" and request.url.path in guarded_paths:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    request_size = int(content_length)
                except ValueError:
                    request_size = 0
                max_request_size = settings.max_upload_size_bytes + REQUEST_SIZE_OVERHEAD_BYTES
                if request_size > max_request_size:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": api_error_detail("file_too_large", "文件超过上传大小限制")},
                    )
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "status_text": status_text("ok")}

    return app


app = create_app()
