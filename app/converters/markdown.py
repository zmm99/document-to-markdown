from pathlib import Path

from app.converters.base import ConvertResult, read_text_file


class MarkdownConverter:
    engine = "markdown"

    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        return ConvertResult(
            markdown=read_text_file(input_path),
            metadata={
                "engine": self.engine,
                "source_format": "markdown",
            },
        )
