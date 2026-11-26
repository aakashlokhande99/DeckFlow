"""Safe HTTP(S) fetcher with SSRF prevention, redirect re-validation, and size limits."""

from __future__ import annotations

import hashlib
from typing import Optional, Set
from urllib.parse import urljoin
import httpx
import structlog
from pydantic import BaseModel

from app.core.security import is_safe_url, validate_url

logger = structlog.get_logger(__name__)

ALLOWED_CONTENT_TYPES: Set[str] = {
    "text/html",
    "application/pdf",
    "text/plain",
    "application/xhtml+xml",
}

DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_TIMEOUT = 12.0
MAX_REDIRECTS = 5


class FetchError(Exception):
    """Base exception for fetch failures."""
    pass


class SSRFBlockedError(FetchError):
    """Raised when a URL or redirect target is blocked by SSRF rules."""
    pass


class ContentSizeExceededError(FetchError):
    """Raised when downloaded response exceeds byte limit."""
    pass


class UnsupportedContentTypeError(FetchError):
    """Raised when response is not HTML, PDF, or text."""
    pass


class FetchResponse(BaseModel):
    """Result of a safe fetch operation."""
    url: str
    canonical_url: str
    status_code: int
    content_type: str
    content_bytes: bytes
    content_hash: str
    byte_count: int


class SafeFetcher:
    """Outbound HTTP client ensuring strict SSRF controls and resource safety."""

    def __init__(
        self,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout: float = DEFAULT_TIMEOUT,
        max_redirects: int = MAX_REDIRECTS,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.max_redirects = max_redirects

    async def fetch(self, url: str) -> FetchResponse:
        """Fetch URL with SSRF protection and re-validated redirects."""
        # 1. Validate initial URL
        try:
            current_url = validate_url(url)
        except ValueError as exc:
            raise SSRFBlockedError(f"SSRF protection blocked URL '{url}': {exc}") from exc

        redirects_count = 0
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (ConsultingAgentBot/0.1; +contact@example.com)",
            "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            while True:
                try:
                    response = await client.get(current_url, headers=headers)
                except httpx.TimeoutException as exc:
                    raise FetchError(f"Fetch request timed out after {self.timeout}s: {exc}") from exc
                except Exception as exc:
                    raise FetchError(f"Network request to '{current_url}' failed: {exc}") from exc

                # Check for redirects
                if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                    redirects_count += 1
                    if redirects_count > self.max_redirects:
                        raise FetchError(f"Too many redirects (exceeded {self.max_redirects}).")

                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("Redirect response missing 'Location' header.")

                    next_url = urljoin(current_url, location)

                    # RE-VALIDATE redirect target to prevent SSRF via open redirects
                    if not is_safe_url(next_url):
                        raise SSRFBlockedError(
                            f"SSRF blocked redirect target: '{next_url}' from origin '{current_url}'"
                        )
                    current_url = next_url
                    continue

                # 2. Check HTTP status
                if response.status_code != 200:
                    raise FetchError(f"HTTP request returned non-200 status: {response.status_code}")

                # 3. Check Content-Type
                raw_content_type = response.headers.get("content-type", "").lower()
                clean_type = raw_content_type.split(";")[0].strip()

                if clean_type and not any(allowed in clean_type for allowed in ALLOWED_CONTENT_TYPES):
                    raise UnsupportedContentTypeError(
                        f"Unsupported content-type: '{raw_content_type}'. Expected HTML or PDF."
                    )

                # 4. Stream / Check content size
                content_bytes = response.content
                if len(content_bytes) > self.max_bytes:
                    raise ContentSizeExceededError(
                        f"Content size {len(content_bytes)} bytes exceeds limit of {self.max_bytes} bytes."
                    )

                # 5. Compute content hash (SHA-256)
                content_hash = hashlib.sha256(content_bytes).hexdigest()

                return FetchResponse(
                    url=current_url,
                    canonical_url=current_url,
                    status_code=response.status_code,
                    content_type=clean_type or "text/html",
                    content_bytes=content_bytes,
                    content_hash=content_hash,
                    byte_count=len(content_bytes),
                )
