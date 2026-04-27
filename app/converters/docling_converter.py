from pathlib import Path

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
            result = DocumentConverter().convert(str(input_path))
            markdown = result.document.export_to_markdown()
        except Exception as exc:
            raise ConversionError("convert_failed", "docling conversion failed") from exc

        return ConvertResult(
            markdown=markdown,
            metadata={
                "engine": self.engine,
                "source_format": self.source_format,
            },
        )
