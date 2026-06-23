import csv
from io import StringIO
from pathlib import Path

from app.converters.base import ConvertResult, read_text_file, rows_to_markdown_table


class CsvConverter:
    engine = "csv"

    def convert(
        self,
        input_path: Path,
        output_dir: Path,
        options: object | None = None,
    ) -> ConvertResult:
        content = read_text_file(input_path)
        reader = csv.reader(StringIO(content))
        rows = [row for row in reader]

        return ConvertResult(
            markdown=rows_to_markdown_table(rows),
            metadata={
                "engine": self.engine,
                "source_format": "csv",
                "rows": len(rows),
            },
        )
