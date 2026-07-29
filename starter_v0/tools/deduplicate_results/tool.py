from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tools._shared import err, fold_text


TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
}


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlsplit(value)
    if not parsed.hostname:
        return value.rstrip("/")

    scheme = parsed.scheme.lower() or "https"
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    try:
        port = parsed.port
    except ValueError:
        port = None
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, item_value)
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    query.sort(key=lambda pair: (pair[0].lower(), pair[1]))
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def _normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", fold_text(title or "")))


def deduplicate_results(
    items: list[dict[str, Any]] | None = None,
    similarity_threshold: float = 0.85,
) -> dict[str, Any]:
    try:
        if items is None:
            items = []
        if not isinstance(items, list):
            raise TypeError("items must be a list")
        threshold = float(similarity_threshold)
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")

        unique_items: list[dict[str, Any]] = []
        unique_keys: list[tuple[str, str]] = []
        duplicates: list[dict[str, Any]] = []

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise TypeError(f"items[{index}] must be an object")
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title:
                raise ValueError(f"items[{index}].title is required")
            if not url:
                raise ValueError(f"items[{index}].url is required")

            normalized_url = _normalize_url(url)
            normalized_title = _normalize_title(title)
            duplicate_of: int | None = None
            reason = ""
            similarity = 0.0

            for kept_index, (kept_url, kept_title) in enumerate(unique_keys):
                if normalized_url and normalized_url == kept_url:
                    duplicate_of = kept_index
                    reason = "same_normalized_url"
                    similarity = 1.0
                    break
                if normalized_title and kept_title:
                    title_similarity = SequenceMatcher(None, normalized_title, kept_title).ratio()
                    if title_similarity >= threshold:
                        duplicate_of = kept_index
                        reason = "similar_title"
                        similarity = title_similarity
                        break

            if duplicate_of is None:
                unique_items.append(dict(item))
                unique_keys.append((normalized_url, normalized_title))
            else:
                duplicates.append({
                    "original_index": index,
                    "duplicate_of_unique_index": duplicate_of,
                    "reason": reason,
                    "similarity": round(similarity, 4),
                    "normalized_url": normalized_url,
                    "item": dict(item),
                })

        return {
            "tool": "deduplicate_results",
            "items": unique_items,
            "duplicates": duplicates,
            "original_count": len(items),
            "unique_count": len(unique_items),
            "removed_count": len(duplicates),
            "similarity_threshold": threshold,
        }
    except Exception as exc:
        return err("deduplicate_results", exc)
