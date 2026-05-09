from pathlib import Path
import re

from app.config import settings
from app.converters.base import ConversionError, ConvertAsset, ConvertResult
from app.converters.docx_converter import DocxConverter


class DoclingConverter:
    engine = "docling"

    def __init__(self, source_format: str) -> None:
        self.source_format = source_format

    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise ConversionError("converter_dependency_missing", "docling is not installed") from exc

        try:
            converter = self._create_converter()
            result = converter.convert(str(input_path))
            markdown, assets = self._export_markdown_with_assets(result.document, output_dir)
        except Exception as exc:
            if self.source_format == "docx":
                return self._convert_docx_with_fallback(input_path, output_dir, exc)
            raise ConversionError("convert_failed", "docling conversion failed") from exc

        return ConvertResult(
            markdown=markdown,
            metadata={
                "engine": self.engine,
                "source_format": self.source_format,
                "ocr_enabled": False if self.source_format == "pdf" else None,
            },
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
            raise ConversionError("convert_failed", "docx conversion failed") from exc

        return ConvertResult(
            markdown=result.markdown,
            metadata={
                **result.metadata,
                "engine": self.engine,
                "fallback_engine": result.metadata["engine"],
            },
            assets=result.assets,
            warnings=["docling failed for docx; used python-docx fallback"],
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

        document_id = output_dir.name
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

    def _create_converter(self):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        if self.source_format != "pdf":
            return DocumentConverter()

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
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
