from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from tools._shared import TIMEOUT, domain, err


MAX_BODY_BYTES = 512 * 1024
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical_url = ""

    @property
    def title(self) -> str:
        return " ".join(" ".join(self._title_parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): (value or "").strip() for key, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._inside_title = True
        elif tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
                or ""
            ).lower()
            content = attributes.get("content", "")
            if key and content:
                self.meta.setdefault(key, content)
        elif tag == "link":
            rel = {value.lower() for value in attributes.get("rel", "").split()}
            href = attributes.get("href", "")
            if "canonical" in rel and href and not self.canonical_url:
                self.canonical_url = href

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title and data.strip():
            self._title_parts.append(data.strip())


def _first(meta: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = meta.get(key)
        if value:
            return value
    return ""


def _validated_public_url(url: str) -> str:
    candidate = (url or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("url must use http or https")
    if not parsed.hostname:
        raise ValueError("url must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("credential-bearing URLs are not allowed")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("url contains an invalid port") from exc
    if port not in {None, 80, 443}:
        raise ValueError("only ports 80 and 443 are allowed")

    hostname = parsed.hostname.rstrip(".")
    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = {literal_ip}
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("hostname could not be resolved") from exc
        addresses = {ipaddress.ip_address(item[4][0]) for item in resolved}

    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("url must resolve only to public IP addresses")

    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def _get_with_validated_redirects(url: str) -> tuple[requests.Response, list[dict[str, Any]]]:
    current_url = url
    redirects: list[dict[str, Any]] = []
    headers = {"User-Agent": "AI20k-Day04-Source-Inspector/1.0"}

    for _ in range(MAX_REDIRECTS + 1):
        current_url = _validated_public_url(current_url)
        try:
            response = requests.get(
                current_url,
                headers=headers,
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise RuntimeError("unable to retrieve the public URL") from exc

        if response.status_code not in REDIRECT_STATUSES:
            return response, redirects

        location = response.headers.get("Location", "").strip()
        if not location:
            return response, redirects
        next_url = urljoin(current_url, location)
        redirects.append({
            "status_code": response.status_code,
            "from": current_url,
            "to": next_url,
        })
        response.close()
        current_url = next_url

    raise RuntimeError(f"more than {MAX_REDIRECTS} redirects")


def _read_limited_text(response: requests.Response) -> tuple[str, bool]:
    chunks: list[bytes] = []
    byte_count = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=16 * 1024):
        if not chunk:
            continue
        remaining = MAX_BODY_BYTES - byte_count
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        byte_count += len(chunk)
        if byte_count >= MAX_BODY_BYTES:
            truncated = True
            break
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace"), truncated


def inspect_source(url: str = "") -> dict[str, Any]:
    response: requests.Response | None = None
    try:
        requested_url = _validated_public_url(url)
        response, redirects = _get_with_validated_redirects(requested_url)
        final_url = _validated_public_url(response.url)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        should_parse_html = not content_type or content_type in {"text/html", "application/xhtml+xml"}

        parser = _PageMetadataParser()
        truncated = False
        if should_parse_html:
            html, truncated = _read_limited_text(response)
            parser.feed(html)

        title = _first(parser.meta, ("og:title", "twitter:title")) or parser.title
        author = _first(parser.meta, ("author", "article:author", "dc.creator", "byl"))
        published_at = _first(parser.meta, (
            "article:published_time",
            "og:published_time",
            "datepublished",
            "date",
            "pubdate",
            "publishdate",
            "dc.date",
            "dc.date.issued",
        ))
        canonical_url = urljoin(final_url, parser.canonical_url) if parser.canonical_url else ""
        uses_https = urlsplit(final_url).scheme.lower() == "https"

        quality_signals: list[str] = []
        warnings: list[str] = []
        if uses_https:
            quality_signals.append("uses_https")
        else:
            warnings.append("does_not_use_https")
        if title:
            quality_signals.append("title_metadata_present")
        else:
            warnings.append("missing_title_metadata")
        if author:
            quality_signals.append("author_metadata_present")
        else:
            warnings.append("missing_author_metadata")
        if published_at:
            quality_signals.append("publication_date_present")
        else:
            warnings.append("missing_publication_date")
        if canonical_url:
            quality_signals.append("canonical_url_present")
        if content_type and not should_parse_html:
            warnings.append("content_is_not_html")
        if response.status_code >= 400:
            warnings.append(f"http_status_{response.status_code}")
        if truncated:
            warnings.append("metadata_scan_truncated")
        if domain(requested_url) != domain(final_url):
            warnings.append("redirected_to_different_domain")

        return {
            "tool": "inspect_source",
            "url": url,
            "final_url": final_url,
            "domain": domain(final_url),
            "status_code": response.status_code,
            "uses_https": uses_https,
            "title": title,
            "author": author,
            "published_at": published_at,
            "canonical_url": canonical_url,
            "content_type": content_type,
            "redirects": redirects,
            "quality_signals": quality_signals,
            "warnings": warnings,
        }
    except Exception as exc:
        return err("inspect_source", exc)
    finally:
        if response is not None:
            response.close()
