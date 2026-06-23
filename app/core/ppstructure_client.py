from __future__ import annotations

import base64
import json
from pathlib import Path
import socket
from typing import Any
from urllib import error, request

from app.config import settings
from app.converters.base import ConversionError


class PPStructureClient:
    def __init__(
        self,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_url = api_url or settings.ppstructure_api_url
        self.timeout_seconds = timeout_seconds or settings.ppstructure_timeout_seconds

    def parse(
        self,
        input_path: Path,
        file_type: int = 0,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        if self.api_url is None:
            raise ConversionError("ppstructure_unavailable", "PP-StructureV3服务未配置")

        payload = {
            "file": base64.b64encode(input_path.read_bytes()).decode("ascii"),
            "fileType": file_type,
            "useSealRecognition": settings.ppstructure_use_seal_recognition,
            "useTableRecognition": settings.ppstructure_use_table_recognition,
            "returnMarkdownImages": True,
            "visualize": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            self.api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(
                http_request,
                timeout=timeout_seconds or self.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            self._raise_http_error(exc)
        except (TimeoutError, socket.timeout) as exc:
            raise ConversionError("ppstructure_timeout", "PP-StructureV3调用超时") from exc
        except OSError as exc:
            raise ConversionError("ppstructure_unavailable", "PP-StructureV3服务不可用") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法") from exc

        if not isinstance(data, dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

        error_code = data.get("errorCode")
        if error_code not in (None, 0, "0"):
            message = str(data.get("errorMsg") or "PP-StructureV3解析失败")
            raise ConversionError("ppstructure_failed", message)

        if not isinstance(data.get("result"), dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

        return data

    def _raise_http_error(self, exc: error.HTTPError) -> None:
        try:
            body = exc.read().decode("utf-8")
            data = json.loads(body)
            message = str(data.get("errorMsg") or "PP-StructureV3解析失败")
        except Exception:
            message = "PP-StructureV3解析失败"

        if exc.code in {408, 504}:
            raise ConversionError("ppstructure_timeout", "PP-StructureV3调用超时") from exc
        raise ConversionError("ppstructure_failed", message) from exc
