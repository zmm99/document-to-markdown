from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.converters.base import ConversionError
from app.core.conversion_options import ConversionOptions


PDF_PREFLIGHT_BYTES = 4 * 1024 * 1024
PDF_IMAGE_MARKERS = (b"/Subtype /Image", b"/Subtype/Image")
PDF_TEXT_MARKERS = (b"/Font", b"/ToUnicode")


@dataclass(frozen=True)
class LayoutDecision:
    actual_layout_engine: str
    ocr_applied: bool
    reason: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PdfPreflight:
    has_text_layer: bool
    has_bitmap_images: bool
    scanned_image_only: bool
    readable: bool = True


def inspect_pdf_preflight(input_path: Path) -> PdfPreflight:
    try:
        with input_path.open("rb") as file_obj:
            content = file_obj.read(PDF_PREFLIGHT_BYTES)
    except OSError:
        return PdfPreflight(
            has_text_layer=False,
            has_bitmap_images=False,
            scanned_image_only=False,
            readable=False,
        )

    has_text_layer = any(marker in content for marker in PDF_TEXT_MARKERS)
    has_bitmap_images = any(marker in content for marker in PDF_IMAGE_MARKERS)
    return PdfPreflight(
        has_text_layer=has_text_layer,
        has_bitmap_images=has_bitmap_images,
        scanned_image_only=has_bitmap_images and not has_text_layer,
    )


def decide_layout(
    file_format: str,
    input_path: Path,
    options: ConversionOptions,
) -> LayoutDecision:
    if options.layout_engine == "ppstructure":
        return _decide_ppstructure(file_format)

    if file_format != "pdf":
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=False,
            reason="non_pdf_format",
        )

    if options.ocr_mode == "off":
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=False,
            reason="ocr_disabled",
        )

    if options.layout_engine == "docling":
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=True,
            reason="requested_docling",
        )

    preflight = inspect_pdf_preflight(input_path)
    if not preflight.readable:
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=True,
            reason="pdf_preflight_unavailable",
            warnings=["PDF预检失败，已使用Docling+RapidOCR"],
        )

    if preflight.scanned_image_only:
        if settings.ppstructure_api_url is not None:
            return LayoutDecision(
                actual_layout_engine="ppstructure",
                ocr_applied=True,
                reason="scanned_pdf_image_only",
            )
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=True,
            reason="ppstructure_unavailable_fallback",
            warnings=["PP-StructureV3服务未配置，已使用Docling+RapidOCR"],
        )

    if preflight.has_text_layer:
        return LayoutDecision(
            actual_layout_engine="docling",
            ocr_applied=True,
            reason="digital_pdf",
        )

    return LayoutDecision(
        actual_layout_engine="docling",
        ocr_applied=True,
        reason="auto_docling_conservative",
    )


def _decide_ppstructure(file_format: str) -> LayoutDecision:
    if file_format != "pdf":
        raise ConversionError("unsupported_file_format", "PP-StructureV3仅支持PDF文件")
    if settings.ppstructure_api_url is None:
        raise ConversionError("ppstructure_unavailable", "PP-StructureV3服务未配置")

    return LayoutDecision(
        actual_layout_engine="ppstructure",
        ocr_applied=True,
        reason="requested_ppstructure",
    )
