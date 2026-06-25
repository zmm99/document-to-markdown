from importlib import resources
from pathlib import Path
import re

from app.config import settings
from app.converters.base import ConversionError, ConvertAsset, ConvertResult
from app.converters.docx_converter import DocxConverter
from app.core.conversion_options import ConversionOptions, parse_conversion_options


RAPIDOCR_MODEL_FILES = {
    "det_model_path": Path("onnx/PP-OCRv5/det/ch_PP-OCRv5_det_server.onnx"),
    "cls_model_path": Path("onnx/PP-OCRv5/cls/ch_PP-LCNet_x1_0_textline_ori_cls_server.onnx"),
    "rec_model_path": Path("onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx"),
}
RAPIDOCR_MODEL_PROFILE = "PP-OCRv5-server-onnx"
RAPIDOCR_BITMAP_AREA_THRESHOLD = 0.05


class DoclingConverter:
    engine = "docling"

    def __init__(self, source_format: str) -> None:
        self.source_format = source_format

    def convert(
        self,
        input_path: Path,
        output_dir: Path,
        options: object | None = None,
    ) -> ConvertResult:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise ConversionError("converter_dependency_missing", "Docling未安装") from exc

        resolved_options = self._resolve_options(options)
        try:
            converter = self._create_converter(resolved_options)
            result = converter.convert(str(input_path))
            markdown, assets = self._export_markdown_with_assets(result.document, output_dir)
        except Exception as exc:
            if self.source_format == "docx":
                return self._convert_docx_with_fallback(input_path, output_dir, exc)
            if isinstance(exc, ConversionError):
                raise
            raise ConversionError("convert_failed", "Docling转换失败") from exc

        return ConvertResult(
            markdown=markdown,
            metadata=self._metadata(resolved_options, input_path),
            assets=assets,
        )

    def _convert_docx_with_fallback(
        self,
        input_path: Path,
        output_dir: Path,
        _original_error: Exception,
    ) -> ConvertResult:
        try:
            result = DocxConverter().convert(input_path, output_dir)
        except Exception as exc:
            raise ConversionError("convert_failed", "DOCX转换失败") from exc

        return ConvertResult(
            markdown=result.markdown,
            metadata={
                **result.metadata,
                "engine": self.engine,
                "fallback_engine": result.metadata["engine"],
            },
            assets=result.assets,
            warnings=["Docling处理DOCX失败，已使用python-docx兜底转换"],
        )

    def _export_markdown_with_assets(self, document, output_dir: Path) -> tuple[str, list[ConvertAsset]]:
        from docling_core.types.doc.base import ImageRefMode
        from PIL import Image

        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for old_asset in assets_dir.glob("*.png"):
            old_asset.unlink()
        markdown_path = output_dir / "result.md"

        document.save_as_markdown(
            markdown_path,
            artifacts_dir=Path("assets"),
            image_mode=ImageRefMode.REFERENCED,
        )
        markdown = markdown_path.read_text(encoding="utf-8")

        document_id = self._document_id_from_output_dir(output_dir)
        asset_url = f"{settings.api_prefix}/documents/{document_id}/assets/"
        assets: list[ConvertAsset] = []
        kept_index = 1

        for path in sorted(assets_dir.glob("*.png")):
            with Image.open(path) as image:
                width, height = image.size

            if width < 120 or height < 80:
                markdown = self._remove_image_link(markdown, path.name)
                path.unlink(missing_ok=True)
                continue

            new_name = f"image-{kept_index:03d}.png"
            new_path = assets_dir / new_name
            if path != new_path:
                if new_path.exists():
                    new_path.unlink()
                path.rename(new_path)
                markdown = markdown.replace(path.name, new_name)

            markdown = markdown.replace(f"](assets/{new_name}", f"]({asset_url}{new_name}")
            markdown = markdown.replace(f"](assets\\{new_name}", f"]({asset_url}{new_name}")
            assets.append(
                ConvertAsset(
                    name=new_name,
                    content_type="image/png",
                    path=new_path.resolve(),
                )
            )
            kept_index += 1

        return markdown, assets

    def _remove_image_link(self, markdown: str, filename: str) -> str:
        escaped_name = re.escape(filename)
        pattern = rf"^\s*!\[[^\]]*\]\(assets[\\/]{escaped_name}\)\s*\r?\n?"
        return re.sub(pattern, "", markdown, flags=re.MULTILINE)

    def _document_id_from_output_dir(self, output_dir: Path) -> str:
        if re.fullmatch(r"[a-f0-9]{64}", output_dir.name):
            return output_dir.parent.name
        return output_dir.name

    def _resolve_options(self, options: object | None) -> ConversionOptions:
        if isinstance(options, ConversionOptions):
            return options
        return parse_conversion_options()

    def _metadata(self, options: ConversionOptions, input_path: Path | None = None) -> dict:
        if self.source_format != "pdf":
            return {
                "engine": self.engine,
                "source_format": self.source_format,
                "layout_engine": self.engine,
                "layout_reason": "non_pdf_format",
                "ocr_enabled": None,
                "ocr_applied": False,
            }

        ocr_enabled = options.ocr_mode != "off"
        force_full_page = options.ocr_mode == "full"
        page_count = self._pdf_page_count(input_path) if input_path is not None else None
        return {
            "engine": self.engine,
            "source_format": self.source_format,
            "layout_engine": self.engine,
            "layout_reason": self._layout_reason(options),
            "ocr_enabled": ocr_enabled,
            "ocr_applied": ocr_enabled,
            "ocr": {
                "backend": "rapidocr" if ocr_enabled else None,
                "mode": options.ocr_mode,
                "model_profile": RAPIDOCR_MODEL_PROFILE if ocr_enabled else None,
                "force_full_page_ocr": force_full_page,
                "bitmap_area_threshold": RAPIDOCR_BITMAP_AREA_THRESHOLD if ocr_enabled else None,
            },
            "pages": {
                "page_count": page_count,
                "source": "pdf_preflight",
                "items": [
                    {
                        "page": page,
                        "markdown_start_line": None,
                        "markdown_end_line": None,
                        "asset_names": [],
                        "ocr_applied": ocr_enabled,
                        "fallback": None,
                    }
                    for page in range(1, page_count + 1)
                ]
                if page_count is not None
                else [],
            },
        }

    def _pdf_page_count(self, input_path: Path) -> int | None:
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(input_path))
            try:
                return len(document)
            finally:
                document.close()
        except Exception:
            return None

    def _layout_reason(self, options: ConversionOptions) -> str:
        if self.source_format != "pdf":
            return "non_pdf_format"
        if options.ocr_mode == "off":
            return "ocr_disabled"
        if options.layout_engine == "docling":
            return "requested_docling"
        if options.layout_engine == "auto":
            return "auto_docling"
        return "requested_ppstructure_pending"

    def _create_converter(self, options: ConversionOptions | None = None):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        resolved_options = options or parse_conversion_options()

        if self.source_format != "pdf":
            return DocumentConverter()

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = resolved_options.ocr_mode != "off"
        if pipeline_options.do_ocr:
            pipeline_options.ocr_options = self._rapidocr_options(resolved_options)
        pipeline_options.do_table_structure = False
        pipeline_options.generate_page_images = True
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 2.0
        if settings.docling_artifacts_path is not None:
            pipeline_options.artifacts_path = settings.docling_artifacts_path

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def _rapidocr_options(self, options: ConversionOptions):
        from rapidocr import ModelType, OCRVersion
        from docling.datamodel.pipeline_options import RapidOcrOptions

        model_paths = self._rapidocr_model_paths()
        rec_keys_path = self._rapidocr_rec_keys_path()
        rapidocr_params = {
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.SERVER,
            "Cls.ocr_version": OCRVersion.PPOCRV5,
            "Cls.model_type": ModelType.SERVER,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.SERVER,
        }
        if rec_keys_path is not None:
            rapidocr_params["Rec.rec_keys_path"] = rec_keys_path

        return RapidOcrOptions(
            lang=["chinese"],
            backend="onnxruntime",
            force_full_page_ocr=options.ocr_mode == "full",
            bitmap_area_threshold=RAPIDOCR_BITMAP_AREA_THRESHOLD,
            det_model_path=str(model_paths["det_model_path"]),
            cls_model_path=str(model_paths["cls_model_path"]),
            rec_model_path=str(model_paths["rec_model_path"]),
            rec_keys_path=rec_keys_path,
            rapidocr_params=rapidocr_params,
        )

    def _rapidocr_model_paths(self) -> dict[str, Path]:
        root = self._rapidocr_model_root()
        if root is None or not root.exists():
            raise ConversionError("ocr_model_missing", "RapidOCR model directory is not configured")

        paths: dict[str, Path] = {}
        for key, relative_path in RAPIDOCR_MODEL_FILES.items():
            path = root / relative_path
            if not path.exists():
                matches = list(root.rglob(relative_path.name))
                if matches:
                    path = matches[0]
            if not path.exists():
                raise ConversionError(
                    "ocr_model_missing",
                    f"RapidOCR model file is missing: {relative_path.name}",
                )
            paths[key] = path.resolve()
        return paths

    def _rapidocr_model_root(self) -> Path | None:
        if settings.rapidocr_model_path is not None:
            return settings.rapidocr_model_path
        local_models = Path("models") / "rapidocr"
        if local_models.exists():
            return local_models
        return None

    def _rapidocr_rec_keys_path(self) -> str | None:
        try:
            keys = resources.files("rapidocr").joinpath("models", "ppocrv5_dict.txt")
        except (ModuleNotFoundError, AttributeError):
            return None
        if keys.is_file():
            return str(keys)
        return None
