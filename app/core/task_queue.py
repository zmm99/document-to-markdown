from __future__ import annotations

import asyncio
from contextlib import suppress

from app.config import settings
from app.converters.base import ConversionError
from app.core.conversion_options import conversion_options_from_json
from app.core.document_operations import convert_stored_document, stored_upload_from_document
from app.db.database import get_connection
from app.db.repository import beijing_now
from app.db.task_repository import (
    get_conversion_task,
    mark_task_running,
    mark_unfinished_tasks_failed,
    update_conversion_task,
)


class ConversionTaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] | None = None
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._workers:
            return

        with get_connection() as conn:
            mark_unfinished_tasks_failed(conn)
            conn.commit()

        self._queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._worker_loop(), name=f"conversion-worker-{index}")
            for index in range(settings.task_worker_count)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with suppress(asyncio.CancelledError):
                await worker
        self._workers = []
        self._queue = None

    async def enqueue(self, task_id: str) -> None:
        if self._queue is None:
            raise RuntimeError("转换任务队列未启动")
        await self._queue.put(task_id)

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            task_id = await self._queue.get()
            try:
                await self._process_task(task_id)
            finally:
                self._queue.task_done()

    async def _process_task(self, task_id: str) -> None:
        with get_connection() as conn:
            task = get_conversion_task(conn, task_id)
            if task is None or task["status"] != "queued":
                return
            if not mark_task_running(conn, task_id):
                conn.commit()
                return
            conn.commit()

        self._update_task(
            task_id,
            {
                "progress": 40,
                "stage": "converting",
                "message": "开始转换文档",
            },
        )

        stored = stored_upload_from_document(task["file_id"])
        if stored is None or not stored.upload_path.exists():
            self._mark_failed(
                task_id,
                "upload_not_found",
                "原始文件不存在",
            )
            return

        try:
            options = conversion_options_from_json(task.get("options_json"))
            result = await convert_stored_document(stored, options)
        except ConversionError as exc:
            if exc.error_code == "convert_timeout":
                self._mark_timeout(task_id, exc.error_code, exc.message)
            else:
                self._mark_failed(task_id, exc.error_code, exc.message)
            return
        except Exception:
            self._mark_failed(
                task_id,
                "convert_failed",
                "文档转换失败",
            )
            return

        self._update_task(
            task_id,
            {
                "file_id": result.document_id,
                "status": "success",
                "progress": 100,
                "stage": "completed",
                "message": "文档转换完成",
                "cached": result.cached,
                "error_code": None,
                "error_message": None,
                "finished_at": beijing_now(),
            },
        )

    def _update_task(self, task_id: str, updates: dict) -> None:
        with get_connection() as conn:
            update_conversion_task(conn, task_id, updates)
            conn.commit()

    def _mark_failed(self, task_id: str, error_code: str, message: str) -> None:
        self._update_task(
            task_id,
            {
                "status": "failed",
                "progress": 100,
                "stage": "failed",
                "message": message,
                "error_code": error_code,
                "error_message": message,
                "finished_at": beijing_now(),
            },
        )

    def _mark_timeout(self, task_id: str, error_code: str, message: str) -> None:
        self._update_task(
            task_id,
            {
                "status": "timeout",
                "progress": 100,
                "stage": "timeout",
                "message": message,
                "error_code": error_code,
                "error_message": message,
                "finished_at": beijing_now(),
            },
        )


task_queue = ConversionTaskQueue()
