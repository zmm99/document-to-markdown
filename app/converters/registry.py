from app.converters.base import ConversionError, Converter
from app.converters.csv_converter import CsvConverter
from app.converters.docling_converter import DoclingConverter
from app.converters.html import HtmlConverter
from app.converters.markdown import MarkdownConverter
from app.converters.text import TxtConverter
from app.converters.xlsx import XlsxConverter


def get_converter(file_format: str) -> Converter:
    converters: dict[str, Converter] = {
        "txt": TxtConverter(),
        "markdown": MarkdownConverter(),
        "csv": CsvConverter(),
        "xlsx": XlsxConverter(),
        "html": HtmlConverter(),
        "pdf": DoclingConverter("pdf"),
        "docx": DoclingConverter("docx"),
        "pptx": DoclingConverter("pptx"),
    }

    converter = converters.get(file_format)
    if converter is None:
        raise ConversionError("unsupported_file_format", "unsupported file format")
    return converter
