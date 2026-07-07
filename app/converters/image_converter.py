from __future__ import annotations

import shutil
from pathlib import Path
import re

from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.converters.base import ConversionError, ConvertAsset, ConvertResult
from app.core.conversion_options import ConversionOptions, parse_conversion_options
from app.core.rapidocr_models import RAPIDOCR_MODEL_PROFILE, rapidocr_direct_params


IMAGE_FORMATS = {"png", "jpg", "jpeg"}


class ImageConverter:
    engine = "image"

    def __init__(self, source_format: str) -> None:
        if source_format not in IMAGE_FORMATS:
            raise ConversionError("unsupported_file_format", "不支持的图片格式")
        self.source_format = source_format

    def convert(
        self,
        input_path: Path,
        output_dir: Path,
        options: object | None = None,
    ) -> ConvertResult:
        resolved_options = options if isinstance(options, ConversionOptions) else parse_conversion_options()
        width, height = self._image_size(input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        asset_name = f"image-001{self._asset_suffix(input_path)}"
        asset_path = assets_dir / asset_name
        shutil.copyfile(input_path, asset_path)

        document_id = self._document_id_from_output_dir(output_dir)
        asset_url = f"{settings.api_prefix}/documents/{document_id}/assets/{asset_name}"
        markdown_parts = [f"![{asset_name}]({asset_url})"]

        ocr_texts: list[str] = []
        ocr_scores: list[float] = []
        ocr_elapsed: float | None = None
        ocr_enabled = resolved_options.ocr_mode != "off"
        if ocr_enabled:
            ocr_texts, ocr_scores, ocr_elapsed = self._run_rapidocr(input_path)
            if ocr_texts:
                markdown_parts.append("\n".join(ocr_texts))

        metadata = {
            "engine": self.engine,
            "source_format": self.source_format,
            "layout_engine": self.engine,
            "layout_reason": self._layout_reason(resolved_options),
            "ocr_enabled": ocr_enabled,
            "ocr_applied": ocr_enabled,
            "ocr": {
                "backend": "rapidocr" if ocr_enabled else None,
                "mode": resolved_options.ocr_mode,
                "model_profile": RAPIDOCR_MODEL_PROFILE if ocr_enabled else None,
                "text_count": len(ocr_texts) if ocr_enabled else 0,
                "average_score": round(sum(ocr_scores) / len(ocr_scores), 6) if ocr_scores else None,
                "elapsed_seconds": ocr_elapsed,
            },
            "image": {
                "width": width,
                "height": height,
                "asset_name": asset_name,
                "content_type": self._content_type(asset_name),
            },
            "pages": {
                "page_count": 1,
                "source": "image_preflight",
                "items": [
                    {
                        "page": 1,
                        "markdown_start_line": 1,
                        "markdown_end_line": len("\n\n".join(markdown_parts).splitlines()),
                        "asset_names": [asset_name],
                        "ocr_applied": ocr_enabled,
                        "fallback": None,
                    }
                ],
            },
        }

        return ConvertResult(
            markdown="\n\n".join(markdown_parts),
            metadata=metadata,
            assets=[
                ConvertAsset(
                    name=asset_name,
                    content_type=self._content_type(asset_name),
                    path=asset_path.resolve(),
                )
            ],
        )

    def _image_size(self, input_path: Path) -> tuple[int, int]:
        try:
            with Image.open(input_path) as image:
                image.verify()
            with Image.open(input_path) as image:
                return image.size
        except (OSError, UnidentifiedImageError) as exc:
            raise ConversionError("invalid_image", "图片文件无法识别") from exc

    def _run_rapidocr(self, input_path: Path) -> tuple[list[str], list[float], float | None]:
        try:
            from rapidocr import RapidOCR

            engine = RapidOCR(params=rapidocr_direct_params())
            result = engine(str(input_path))
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError("ocr_failed", "图片OCR失败") from exc

        texts = [str(text).strip() for text in getattr(result, "txts", ()) if str(text).strip()]
        scores = [float(score) for score in getattr(result, "scores", ()) if score is not None]
        elapsed = getattr(result, "elapse", None)
        return texts, scores, float(elapsed) if elapsed is not None else None

    def _layout_reason(self, options: ConversionOptions) -> str:
        if options.ocr_mode == "off":
            return "ocr_disabled"
        return "image_ocr"

    def _asset_suffix(self, input_path: Path) -> str:
        suffix = input_path.suffix.lower()
        if suffix == ".jpeg":
            return ".jpg"
        if suffix in {".png", ".jpg"}:
            return suffix
        return ".png"

    def _content_type(self, asset_name: str) -> str:
        suffix = Path(asset_name).suffix.lower()
        if suffix == ".png":
            return "image/png"
        return "image/jpeg"

    def _document_id_from_output_dir(self, output_dir: Path) -> str:
        if re.fullmatch(r"[a-f0-9]{64}", output_dir.name):
            return output_dir.parent.name
        return output_dir.name
