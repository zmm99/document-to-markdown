from __future__ import annotations

from collections.abc import Iterable

from app.config import settings


def document_url(document_id: str, suffix: str) -> str:
    return f"{settings.api_prefix}/documents/{document_id}/{suffix}"


def asset_url(document_id: str, asset_name: str, option_hash: str | None = None) -> str:
    url = document_url(document_id, f"assets/{asset_name}")
    if option_hash:
        return f"{url}?option_hash={option_hash}"
    return url


def rewrite_asset_urls_to_relative(
    markdown: str,
    document_id: str,
    asset_names: Iterable[str],
    option_hash: str | None = None,
) -> str:
    text = markdown
    for asset_name in asset_names:
        relative_path = f"assets/{asset_name}"
        candidates = [
            asset_url(document_id, asset_name, option_hash),
            asset_url(document_id, asset_name),
        ]
        for candidate in candidates:
            text = text.replace(candidate, relative_path)
    return text
