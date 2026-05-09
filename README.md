# DocumentToMarkdown

DocumentToMarkdown is a lightweight API service for converting digital documents to Markdown.

Current v1.0 scope:

- FastAPI service skeleton.
- SQLite database initialization.
- Local date-based upload and output directories.
- Snowflake-style file id with md5 kept only for internal cache lookup.
- Basic file validation and storage helpers.
- Basic converters for TXT, Markdown, CSV, XLSX, and HTML.
- Docling-based converters for PDF, DOCX, and PPTX.

OCR, async queues, authentication, and object storage are implemented in later phases.
Keep the service on localhost or a trusted internal network unless authentication is added.

## Setup

```powershell
python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run Service

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The service exposes:

- `GET /health`
- `POST /api/documents/convert`
- `GET /api/documents/{file_id}`
- `GET /api/documents/{file_id}/markdown`
- `GET /api/documents/{file_id}/assets/{asset_name}`
- `GET /api/documents/{file_id}/download`
- `DELETE /api/documents/{file_id}/cache`

Useful `.env` options:

```text
MAX_UPLOAD_SIZE_MB=100
CONVERT_TIMEOUT_SECONDS=300
MAX_CONCURRENT_CONVERSIONS=2
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

## Publish Release

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-release.ps1
```

The script runs tests, creates `release/DocumentToMarkdown-v{version}/`, and writes `release/DocumentToMarkdown-v{version}.zip`.
