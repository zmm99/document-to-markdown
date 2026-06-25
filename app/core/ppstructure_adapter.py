from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path
import re
from urllib import error, request
from urllib.parse import quote, urljoin, urlparse

from app.config import settings
from app.converters.base import ConversionError, ConvertAsset, ConvertResult


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_URL_IMAGE_MAX_BYTES = 20 * 1024 * 1024
_URL_IMAGE_TIMEOUT_SECONDS = 30


def adapt_ppstructure_response(
    response: dict,
    output_dir: Path,
    source_format: str,
) -> ConvertResult:
    result = _extract_result(response)
    layout_results = result.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    document_id = _document_id_from_output_dir(output_dir)
    markdown_parts: list[str] = []
    assets: list[ConvertAsset] = []
    warnings: list[str] = []
    pruned_results: list[object] = []
    page_items: list[dict[str, object]] = []
    markdown_image_count = 0
    next_markdown_line = 1

    for page_index, page_result in enumerate(layout_results, start=1):
        if not isinstance(page_result, dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
        markdown = page_result.get("markdown")
        if not isinstance(markdown, dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

        text = markdown.get("text")
        if not isinstance(text, str):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

        images = markdown.get("images") or {}
        if not isinstance(images, dict):
            raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")

        page_asset_names: list[str] = []
        for original_name, encoded_image in images.items():
            if not isinstance(original_name, str) or not isinstance(encoded_image, str):
                raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
            if _looks_like_url(encoded_image):
                resolved_url = _resolve_ppstructure_image_url(encoded_image)
                if resolved_url is None:
                    warnings.append("PP-StructureV3返回非服务图片URL，当前未下载")
                    continue
                downloaded = _download_ppstructure_image_url(original_name, resolved_url)
                if downloaded is None:
                    warnings.append("PP-StructureV3服务图片URL下载失败，当前未下载")
                    continue
                image_bytes, mime_type, suffix = downloaded
            else:
                image_bytes, mime_type, suffix = _decode_image(original_name, encoded_image)

            markdown_image_count += 1
            asset_name = f"image-{len(assets) + 1:03d}{suffix}"
            asset_path = assets_dir / asset_name
            asset_path.write_bytes(image_bytes)
            asset_url = f"{settings.api_prefix}/documents/{document_id}/assets/{asset_name}"
            text = _replace_markdown_image_path(text, original_name, asset_url)
            assets.append(
                ConvertAsset(
                    name=asset_name,
                    content_type=mime_type,
                    path=asset_path.resolve(),
                )
            )
            page_asset_names.append(asset_name)

        page_text = text.strip()
        markdown_start_line: int | None = None
        markdown_end_line: int | None = None
        if page_text:
            markdown_start_line = next_markdown_line
            markdown_end_line = markdown_start_line + page_text.count("\n")
            next_markdown_line = markdown_end_line + 3
            markdown_parts.append(page_text)

        page_fallback = None
        if "prunedResult" in page_result:
            pruned_result = page_result["prunedResult"]
            pruned_results.append(pruned_result)
            if isinstance(pruned_result, dict):
                page_fallback = pruned_result.get("fallback")

        page_items.append(
            {
                "page": page_index,
                "markdown_start_line": markdown_start_line,
                "markdown_end_line": markdown_end_line,
                "asset_names": page_asset_names,
                "ocr_applied": True,
                "fallback": page_fallback,
            }
        )

    metadata = {
        "engine": "ppstructure",
        "source_format": source_format,
        "layout_engine": "ppstructure",
        "layout_reason": "requested_ppstructure",
        "ocr_enabled": True,
        "ocr_applied": True,
        "ppstructure": {
            "api_url": settings.ppstructure_api_url,
            "page_count": len(layout_results),
            "markdown_image_count": markdown_image_count,
            "saved_asset_count": len(assets),
            "use_table_recognition": settings.ppstructure_use_table_recognition,
            "use_seal_recognition": settings.ppstructure_use_seal_recognition,
            "log_id": response.get("logId"),
            "data_info": result.get("dataInfo") or {},
        },
        "pages": {
            "page_count": len(layout_results),
            "source": "ppstructure",
            "items": page_items,
        },
        "pruned_results": pruned_results,
    }

    return ConvertResult(
        markdown="\n\n".join(markdown_parts),
        metadata=metadata,
        assets=assets,
        warnings=warnings,
    )


def _extract_result(response: dict) -> dict:
    if not isinstance(response, dict):
        raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
    if "layoutParsingResults" in response:
        return response
    result = response.get("result")
    if not isinstance(result, dict):
        raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法")
    return result


def _decode_image(original_name: str, encoded_image: str) -> tuple[bytes, str, str]:
    mime_type, payload = _split_data_url(encoded_image)
    suffix = _suffix_for_image(original_name, mime_type)
    if mime_type is None:
        mime_type = mimetypes.guess_type(f"image{suffix}")[0] or "application/octet-stream"

    try:
        return base64.b64decode(payload, validate=True), mime_type, suffix
    except (binascii.Error, ValueError) as exc:
        raise ConversionError("ppstructure_invalid_response", "PP-StructureV3响应结构不合法") from exc


def _download_ppstructure_image_url(original_name: str, image_url: str) -> tuple[bytes, str, str] | None:
    try:
        http_request = request.Request(image_url, method="GET")
        with request.urlopen(http_request, timeout=_URL_IMAGE_TIMEOUT_SECONDS) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith("image/"):
                return None
            chunks: list[bytes] = []
            total_size = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > _URL_IMAGE_MAX_BYTES:
                    return None
                chunks.append(chunk)
    except (OSError, TimeoutError, error.URLError, error.HTTPError):
        return None

    image_bytes = b"".join(chunks)
    if not image_bytes:
        return None

    mime_type = content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    suffix = _suffix_for_image(original_name, mime_type)
    return image_bytes, mime_type, suffix


def _resolve_ppstructure_image_url(image_url: str) -> str | None:
    api_url = settings.ppstructure_api_url
    if not api_url:
        return None

    resolved_url = urljoin(api_url, image_url.strip())
    image_parts = urlparse(resolved_url)
    service_parts = urlparse(api_url)
    if (
        image_parts.scheme not in {"http", "https"}
        or image_parts.scheme != service_parts.scheme
        or image_parts.hostname != service_parts.hostname
        or _effective_port(image_parts) != _effective_port(service_parts)
    ):
        return None
    return resolved_url


def _effective_port(parts) -> int | None:
    if parts.port is not None:
        return parts.port
    if parts.scheme == "http":
        return 80
    if parts.scheme == "https":
        return 443
    return None


def _split_data_url(value: str) -> tuple[str | None, str]:
    match = re.fullmatch(r"data:([^;]+);base64,(.+)", value.strip(), flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).lower(), match.group(2)
    return None, value


def _suffix_for_image(original_name: str, mime_type: str | None) -> str:
    if mime_type:
        suffix = mimetypes.guess_extension(mime_type) or ""
        if suffix == ".jpe":
            return ".jpg"
        if suffix in _IMAGE_SUFFIXES:
            return ".jpg" if suffix == ".jpeg" else suffix

    suffix = Path(original_name).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in _IMAGE_SUFFIXES:
        return suffix
    return ".png"


def _replace_markdown_image_path(markdown: str, original_name: str, asset_url: str) -> str:
    candidates = {
        original_name,
        original_name.replace("\\", "/"),
        original_name.replace("/", "\\"),
        f"./{original_name}",
        quote(original_name),
    }
    text = markdown
    for candidate in sorted(candidates, key=len, reverse=True):
        text = text.replace(candidate, asset_url)
    return text


def _document_id_from_output_dir(output_dir: Path) -> str:
    if re.fullmatch(r"[a-f0-9]{64}", output_dir.name):
        return output_dir.parent.name
    return output_dir.name


def _looks_like_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))
