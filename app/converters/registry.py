from app.converters.base import ConversionError, Converter
from app.converters.csv_converter import CsvConverter
from app.converters.docling_converter import DoclingConverter
from app.converters.html import HtmlConverter
from app.converters.markdown import MarkdownConverter
from app.converters.ppstructure_converter import PPStructureConverter
from app.converters.text import TxtConverter
from app.converters.xlsx import XlsxConverter


def get_converter(file_format: str, layout_engine: str | None = None) -> Converter:
    if layout_engine == "ppstructure":
        if file_format != "pdf":
            raise ConversionError("unsupported_file_format", "PP-StructureV3仅支持PDF文件")
        return PPStructureConverter(file_format)

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
        raise ConversionError("unsupported_file_format", "不支持的文件格式")
    return converter
