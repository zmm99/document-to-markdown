from __future__ import annotations

import base64
from io import BytesIO
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from app.converters.base import ConversionError, ConvertResult
from app.core.ppstructure_adapter import adapt_ppstructure_response
from app.core.ppstructure_client import PPStructureClient


FILE_TYPE_PDF = 0


class PPStructureConverter:
    engine = "ppstructure"

    def __init__(self, source_format: str, client: PPStructureClient | None = None) -> None:
        self.source_format = source_format
        self.client = client or PPStructureClient()

    def convert(
        self,
        input_path: Path,
        output_dir: Path,
        options: object | None = None,
    ) -> ConvertResult:
        _ = options
        if self.source_format != "pdf":
            raise ConversionError("unsupported_file_format", "PP-StructureV3仅支持PDF文件")

        page_count = self._pdf_page_count(input_path)
        if page_count >= settings.ppstructure_page_retry_min_pages:
            return self._convert_with_page_retry(
                input_path,
                output_dir,
                page_count,
                reason="large_pdf",
            )

        try:
            response = self.client.parse(
                input_path,
                file_type=FILE_TYPE_PDF,
                timeout_seconds=min(
                    settings.ppstructure_timeout_seconds,
                    settings.ppstructure_full_parse_timeout_seconds,
                ),
            )
            return adapt_ppstructure_response(response, output_dir, self.source_format)
        except ConversionError as exc:
            if exc.error_code != "ppstructure_timeout":
                raise

        return self._convert_with_page_retry(
            input_path,
            output_dir,
            page_count,
            reason="full_parse_timeout",
        )

    def _pdf_page_count(self, input_path: Path) -> int:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise ConversionError("converter_dependency_missing", "pypdfium2未安装") from exc

        try:
            pdf = pdfium.PdfDocument(str(input_path))
            try:
                return len(pdf)
            finally:
                pdf.close()
        except Exception as exc:
            raise ConversionError("convert_failed", "PDF页面预检失败") from exc

    def _convert_with_page_retry(
        self,
        input_path: Path,
        output_dir: Path,
        page_count: int,
        reason: str,
    ) -> ConvertResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        combined_results: list[dict[str, Any]] = []
        fallback_pages: list[dict[str, Any]] = []

        temp_root = output_dir.parent / f"pp-pages-{uuid4().hex}"
        temp_root.mkdir(parents=True, exist_ok=False)
        try:
            for page_index in range(page_count):
                page_pdf = self._render_page_pdf(input_path, page_index, temp_root)
                page_info: dict[str, Any] = {
                    "page": page_index + 1,
                    "preprocessed": False,
                }
                try:
                    page_response = self.client.parse(
                        page_pdf,
                        file_type=FILE_TYPE_PDF,
                        timeout_seconds=settings.ppstructure_page_retry_timeout_seconds,
                    )
                except ConversionError as exc:
                    if (
                        exc.error_code != "ppstructure_timeout"
                        or not settings.ppstructure_preprocess_retry_enabled
                    ):
                        raise
                    preprocessed_pdf = self._preprocess_page_pdf(
                        input_path,
                        page_index,
                        temp_root,
                    )
                    try:
                        page_response = self.client.parse(
                            preprocessed_pdf,
                            file_type=FILE_TYPE_PDF,
                            timeout_seconds=settings.ppstructure_page_retry_timeout_seconds,
                        )
                    except ConversionError as retry_exc:
                        if (
                            retry_exc.error_code != "ppstructure_timeout"
                            or not settings.ppstructure_page_image_fallback_enabled
                        ):
                            raise
                        combined_results.append(
                            self._image_fallback_page_result(input_path, page_index)
                        )
                        page_info["image_fallback"] = True
                        page_info["retry_reason"] = "preprocess_timeout"
                        fallback_pages.append(page_info)
                        continue

                    page_info["preprocessed"] = True
                    page_info["retry_reason"] = "page_timeout"

                combined_results.extend(self._layout_results(page_response))
                fallback_pages.append(page_info)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        response = {
            "logId": "paged-retry",
            "result": {
                "layoutParsingResults": combined_results,
                "dataInfo": {
                    "numPages": page_count,
                    "fallback": "paged_retry",
                },
            },
        }
        result = adapt_ppstructure_response(response, output_dir, self.source_format)
        result.metadata["ppstructure"]["fallback"] = {
            "mode": "paged_retry",
            "reason": reason,
            "page_count": page_count,
            "page_timeout_seconds": settings.ppstructure_page_retry_timeout_seconds,
            "preprocess_retry_enabled": settings.ppstructure_preprocess_retry_enabled,
            "preprocessed_pages": [
                page["page"] for page in fallback_pages if page.get("preprocessed")
            ],
            "image_fallback_pages": [
                page["page"] for page in fallback_pages if page.get("image_fallback")
            ],
            "pages": fallback_pages,
        }
        warnings = [*result.warnings, self._fallback_warning(reason)]
        if any(page.get("image_fallback") for page in fallback_pages):
            warnings.append("PP-StructureV3部分页面OCR超时，已保留为图片")
        return ConvertResult(
            markdown=result.markdown,
            metadata=result.metadata,
            assets=result.assets,
            warnings=warnings,
        )

    def _fallback_warning(self, reason: str) -> str:
        if reason == "large_pdf":
            return "PP-StructureV3大页数PDF已按页解析"
        return "PP-StructureV3整份解析超时，已按页重试"

    def _render_page_pdf(
        self,
        input_path: Path,
        page_index: int,
        temp_root: Path,
    ) -> Path:
        image = self._render_page_image(input_path, page_index)
        page_pdf = temp_root / f"page-{page_index + 1:04d}.pdf"
        try:
            image.save(
                page_pdf,
                "PDF",
                resolution=72.0 * settings.ppstructure_render_scale,
                quality=85,
            )
        finally:
            image.close()
        return page_pdf

    def _preprocess_page_pdf(
        self,
        input_path: Path,
        page_index: int,
        temp_root: Path,
    ) -> Path:
        image = self._render_page_image(input_path, page_index)
        page_pdf = temp_root / f"page-{page_index + 1:04d}-preprocessed.pdf"
        grayscale = None
        binary = None
        binary_rgb = None
        try:
            grayscale = image.convert("L")
            threshold = settings.ppstructure_preprocess_threshold
            binary = grayscale.point(lambda pixel: 255 if pixel > threshold else 0, mode="1")
            binary_rgb = binary.convert("RGB")
            binary_rgb.save(
                page_pdf,
                "PDF",
                resolution=72.0 * settings.ppstructure_render_scale,
                quality=85,
            )
        finally:
            for generated_image in (binary_rgb, binary, grayscale):
                if generated_image is not None:
                    generated_image.close()
            image.close()
        return page_pdf

    def _render_page_image(self, input_path: Path, page_index: int):
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise ConversionError("converter_dependency_missing", "pypdfium2未安装") from exc

        try:
            pdf = pdfium.PdfDocument(str(input_path))
            try:
                page = pdf[page_index]
                try:
                    bitmap = page.render(scale=settings.ppstructure_render_scale)
                    try:
                        return bitmap.to_pil().convert("RGB")
                    finally:
                        close_bitmap = getattr(bitmap, "close", None)
                        if close_bitmap is not None:
                            close_bitmap()
                finally:
                    close_page = getattr(page, "close", None)
                    if close_page is not None:
                        close_page()
            finally:
                pdf.close()
        except Exception as exc:
            raise ConversionError("convert_failed", "PDF页面渲染失败") from exc

    def _image_fallback_page_result(self, input_path: Path, page_index: int) -> dict[str, Any]:
        image = self._render_page_image(input_path, page_index)
        try:
            max_side = settings.ppstructure_page_image_fallback_max_side
            image.thumbnail((max_side, max_side))
            buffer = BytesIO()
            image.save(buffer, "JPEG", quality=85)
        finally:
            image.close()

        image_name = f"page-fallback-{page_index + 1:04d}.jpg"
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {
            "markdown": {
                "text": f"![第{page_index + 1}页]({image_name})",
                "images": {
                    image_name: f"data:image/jpeg;base64,{encoded}",
                },
            },
            "prunedResult": {
                "page": page_index + 1,
                "fallback": "image_preserved_after_ocr_timeout",
            },
        }

    def _layout_results(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        result = response.get("result")
        if not isinstance(result, dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
        layout_results = result.get("layoutParsingResults")
        if not isinstance(layout_results, list):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
        for page_result in layout_results:
            if not isinstance(page_result, dict):
                raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
        return layout_results
