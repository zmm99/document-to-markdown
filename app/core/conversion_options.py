from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.file_utils import FileValidationError
from app.core.storage import StoredUpload


OCR_MODES = {"off", "auto", "full"}
LAYOUT_ENGINES = {"docling", "ppstructure", "auto"}


def _normalize_choice(value: str | None, default: str) -> str:
    normalized = (value or default).strip().lower()
    return normalized


def _option_payload(ocr_mode: str, layout_engine: str) -> dict[str, Any]:
    return {
        "version": 1,
        "requested": {
            "ocr_mode": ocr_mode,
            "layout_engine": layout_engine,
        },
        "model_profile": {
            "docling_ocr_backend": "rapidocr",
            "rapidocr_model_profile": "PP-OCRv5-server-onnx",
            "ppstructure": "external_service",
        },
        "routing_profile": {
            "version": 1,
            "auto_pdf_policy": "scan_image_ppstructure_v2",
            "ppstructure_adapter": "v1",
        },
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConversionOptions:
    def __init__(self, ocr_mode: str, layout_engine: str) -> None:
        if ocr_mode not in OCR_MODES:
            raise FileValidationError("invalid_ocr_mode", "OCR模式不合法")
        if layout_engine not in LAYOUT_ENGINES:
            raise FileValidationError("invalid_layout_engine", "版面解析引擎不合法")
        if ocr_mode == "off" and layout_engine == "ppstructure":
            raise FileValidationError(
                "conflicting_layout_options",
                "ocr_mode=off时不能使用PP-StructureV3",
            )

        self.ocr_mode = ocr_mode
        self.layout_engine = layout_engine
        self._payload = _option_payload(ocr_mode, layout_engine)
        self.option_hash = _hash_payload(self._payload)

    @property
    def requested(self) -> dict[str, str]:
        return dict(self._payload["requested"])

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload,
            "option_hash": self.option_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_conversion_options(
    ocr_mode: str | None = None,
    layout_engine: str | None = None,
) -> ConversionOptions:
    return ConversionOptions(
        _normalize_choice(ocr_mode, settings.ocr_default_mode),
        _normalize_choice(layout_engine, settings.layout_engine_default),
    )


def conversion_options_from_json(options_json: str | None) -> ConversionOptions:
    if not options_json:
        return parse_conversion_options("off", "docling")
    try:
        data = json.loads(options_json)
        requested = data.get("requested") or {}
        return parse_conversion_options(
            requested.get("ocr_mode"),
            requested.get("layout_engine"),
        )
    except (TypeError, json.JSONDecodeError, AttributeError) as exc:
        raise FileValidationError("invalid_conversion_options", "转换参数不合法") from exc


def legacy_option_hash() -> str:
    return ConversionOptions("off", "docling").option_hash


def output_dir_for_options(base_output_dir: Path, options: ConversionOptions) -> Path:
    return base_output_dir / options.option_hash


def stored_upload_for_options(stored: StoredUpload, options: ConversionOptions) -> StoredUpload:
    output_dir = output_dir_for_options(stored.output_dir, options)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assets").mkdir(parents=True, exist_ok=True)
    return replace(stored, output_dir=output_dir)


def metadata_with_options(
    metadata: dict[str, Any],
    options: ConversionOptions,
    actual_layout_engine: str = "docling",
    ocr_applied: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    if reason is None:
        if options.ocr_mode == "off":
            reason = "ocr_disabled"
        elif options.layout_engine == "docling":
            reason = "requested_docling"
        elif options.layout_engine == "ppstructure":
            reason = "requested_ppstructure_pending"
        else:
            reason = "layout_routing_pending"

    return {
        **metadata,
        "requested": options.requested,
        "actual": {
            "layout_engine": actual_layout_engine,
            "ocr_applied": ocr_applied,
            "reason": reason,
        },
        "option_hash": options.option_hash,
    }
