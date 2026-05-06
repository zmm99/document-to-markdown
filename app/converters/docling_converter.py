from pathlib import Path

from app.config import settings
from app.converters.base import ConversionError, ConvertResult


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
            markdown = result.document.export_to_markdown()
        except Exception as exc:
            raise ConversionError("convert_failed", "docling conversion failed") from exc

        return ConvertResult(
            markdown=markdown,
            metadata={
                "engine": self.engine,
                "source_format": self.source_format,
                "ocr_enabled": False if self.source_format == "pdf" else None,
            },
        )

    def _create_converter(self):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        if self.source_format != "pdf":
            return DocumentConverter()

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        if settings.docling_artifacts_path is not None:
            pipeline_options.artifacts_path = settings.docling_artifacts_path

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
