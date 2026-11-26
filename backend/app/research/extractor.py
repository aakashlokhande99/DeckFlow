"""Text extraction and prompt-injection sanitization for HTML and PDF content."""

from __future__ import annotations

import io
import re
import structlog
from bs4 import BeautifulSoup
from pypdf import PdfReader

logger = structlog.get_logger(__name__)

# Injection patterns to neutralize or strip from retrieved external content
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+all\s+previous\s+instructions\b"),
    re.compile(r"(?i)\bignore\s+the\s+above\s+and\s+do\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+in\s+developer\s+mode\b"),
    re.compile(r"(?i)<\s*\|\s*im_start\s*\|.*?>"),
    re.compile(r"(?i)\[\s*system\s*:\s*prompt\s*override\s*\]"),
    re.compile(r"(?i)\bdisregard\s+prior\s+guidelines\b"),
]


def sanitize_text(text: str) -> str:
    """Neutralize prompt injection vectors and normalize whitespaces."""
    if not text:
        return ""

    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED_INJECTION_ATTEMPT]", sanitized)

    # Collapse multiple consecutive empty lines and trailing spaces
    sanitized = re.sub(r"[ \t]+", " ", sanitized)
    sanitized = re.sub(r"\n\s*\n\s*\n+", "\n\n", sanitized)
    return sanitized.strip()


def extract_text_from_html(html_bytes: bytes) -> str:
    """Extract clean prose text from raw HTML, stripping scripts, navigation, and boilerplate."""
    if not html_bytes:
        return ""

    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception:
        soup = BeautifulSoup(html_bytes, "html.parser")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside", "form", "svg"]):
        tag.decompose()

    # Extract text with line breaks between blocks
    text = soup.get_text(separator="\n", strip=True)
    return sanitize_text(text)


def extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 50) -> str:
    """Extract text from PDF document up to max_pages."""
    if not pdf_bytes:
        return ""

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text: list[str] = []

        total_pages = min(len(reader.pages), max_pages)
        for i in range(total_pages):
            page_content = reader.pages[i].extract_text()
            if page_content:
                pages_text.append(page_content)

        raw_text = "\n\n".join(pages_text)
        return sanitize_text(raw_text)
    except Exception as exc:
        logger.warning("pdf_extraction_failed", error=str(exc))
        return ""


def extract_content(content_bytes: bytes, content_type: str) -> str:
    """Route extraction according to content_type."""
    clean_type = content_type.lower()
    if "pdf" in clean_type:
        return extract_text_from_pdf(content_bytes)
    return extract_text_from_html(content_bytes)
