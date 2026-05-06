# DocumentToMarkdown

DocumentToMarkdown is a lightweight API service for converting digital documents to Markdown.

Current v1.0 scope:

- FastAPI service skeleton.
- SQLite database initialization.
- Local date-based upload and output directories.
- md5-based file id.
- Basic file validation and storage helpers.
- Basic converters for TXT, Markdown, CSV, XLSX, and HTML.
- Docling-based converters for PDF, DOCX, and PPTX.

OCR, async queues, and object storage are implemented in later phases.

## Setup

```powershell
python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Docling Models

PDF conversion uses Docling layout models. Prefetch them before running the service in production or offline environments:

```powershell
.\.venv\Scripts\docling-tools.exe models download --output-dir ./models/docling
```

Then configure:

```powershell
DOCLING_ARTIFACTS_PATH=./models/docling
```

## Run Checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```
