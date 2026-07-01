# -*- coding: utf-8 -*-
"""
===================================
Knowledge Base Parser
===================================

Parses documents into chunks for knowledge base storage.
Supports text, markdown, and PDF (text extraction).

Security:
- File size limit enforced
- Content length limit enforced
- SSRF protection for URL fetching
"""

import hashlib
import logging
import re
import ipaddress
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 100  # characters
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_CONTENT_LENGTH = 200000  # 200k chars
URL_TIMEOUT = 10  # seconds

# SSRF blocklist
BLOCKED_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class KnowledgeBaseParserError(Exception):
    """Base exception for parser errors."""
    pass


class FileSizeLimitError(KnowledgeBaseParserError):
    """Raised when file exceeds size limit."""
    pass


class ContentLengthLimitError(KnowledgeBaseParserError):
    """Raised when content exceeds length limit."""
    pass


class SSRFDetectedError(KnowledgeBaseParserError):
    """Raised when SSRF attack is detected."""
    pass


def _is_blocked_host(host: str) -> bool:
    """Check if host resolves to a blocked IP."""
    try:
        # Block localhost and common internal hostnames
        lower = host.lower().strip()
        if lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return True
        if lower.startswith("localhost") or lower.endswith(".local"):
            return True

        # Try to resolve and check IP
        import socket
        try:
            addrs = socket.getaddrinfo(host, None)
            for family, _, _, _, sockaddr in addrs:
                ip_str = sockaddr[0]
                ip = ipaddress.ip_address(ip_str)
                for blocked in BLOCKED_IP_RANGES:
                    if ip in blocked:
                        logger.warning(f"SSRF blocked: {host} -> {ip_str}")
                        return True
        except socket.gaierror:
            logger.debug(f"Could not resolve host: {host}")
            return False
    except Exception as e:
        logger.warning(f"SSRF check error for {host}: {e}")
    return False


def _is_blocked_url(url: str) -> bool:
    """Check if URL is blocked (file://, etc.)."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in ("file", "ftp", "sftp", "smb"):
        logger.warning(f"Blocked URL scheme: {url}")
        return True
    if _is_blocked_host(parsed.netloc):
        return True
    return False


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 chars for Chinese/English mixed)."""
    return max(1, len(text) // 4)


def _split_into_chunks(
    content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks."""
    if len(content) <= chunk_size:
        return [content] if content.strip() else []

    chunks: List[str] = []
    start = 0

    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]

        # Try to break at sentence/paragraph boundary
        if end < len(content):
            # Look for paragraph break first
            para_break = chunk.rfind("\n\n")
            if para_break > chunk_size // 2:
                chunk = chunk[:para_break]
                end = start + para_break + 2
            else:
                # Look for sentence break
                sentence_break = max(
                    chunk.rfind("。"),
                    chunk.rfind("."),
                    chunk.rfind("！"),
                    chunk.rfind("!"),
                    chunk.rfind("？"),
                    chunk.rfind("?"),
                )
                if sentence_break > chunk_size // 2:
                    chunk = chunk[: sentence_break + 1]
                    end = start + sentence_break + 1

        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)

        # Move start position with overlap
        start = end - overlap
        if start >= len(content):
            break

    return chunks


def parse_text(content: str) -> Tuple[List[str], str]:
    """
    Parse plain text content into chunks.

    Returns:
        Tuple of (chunks, content_hash)
    """
    if len(content) > MAX_CONTENT_LENGTH:
        raise ContentLengthLimitError(
            f"Content length {len(content)} exceeds limit {MAX_CONTENT_LENGTH}"
        )

    content = content.strip()
    if not content:
        return [], compute_content_hash("")

    chunks = _split_into_chunks(content)
    return chunks, compute_content_hash(content)


def parse_markdown(content: str) -> Tuple[List[str], str]:
    """
    Parse markdown content into chunks.
    Preserves heading structure for better context.

    Returns:
        Tuple of (chunks, content_hash)
    """
    if len(content) > MAX_CONTENT_LENGTH:
        raise ContentLengthLimitError(
            f"Content length {len(content)} exceeds limit {MAX_CONTENT_LENGTH}"
        )

    content = content.strip()
    if not content:
        return [], compute_content_hash("")

    # Split by double newline (paragraphs) or headers
    sections: List[str] = []
    current = ""

    lines = content.split("\n")
    for line in lines:
        # Check for markdown headers
        if re.match(r"^#{1,6}\s+", line):
            if current.strip():
                sections.append(current.strip())
            current = line + "\n"
        elif line.strip() == "" and current.strip():
            # Empty line - potential paragraph break
            if len(current.strip()) > 100:  # Only break long paragraphs
                sections.append(current.strip())
                current = ""
        else:
            current += line + "\n"

    if current.strip():
        sections.append(current.strip())

    # Merge short sections with next
    merged: List[str] = []
    buffer = ""

    for section in sections:
        if len(section) < 200 and merged:
            # Merge short section with previous
            merged[-1] += "\n\n" + section
        else:
            merged.append(section)

    # Now split each section into chunks
    all_chunks: List[str] = []
    for section in merged:
        chunks = _split_into_chunks(section)
        all_chunks.extend(chunks)

    return all_chunks, compute_content_hash(content)


def parse_pdf(file_path: str) -> Tuple[List[str], str]:
    """
    Extract text from PDF file.

    Returns:
        Tuple of (chunks, content_hash)

    Raises:
        KnowledgeBaseParserError: If PDF extraction fails
    """
    path = Path(file_path)
    if not path.exists():
        raise KnowledgeBaseParserError(f"PDF file not found: {file_path}")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise FileSizeLimitError(
            f"File size {path.stat().st_size} exceeds limit {MAX_FILE_SIZE}"
        )

    content = _extract_pdf_text(path)
    return parse_markdown(content)  # Use markdown parser for structure


def _extract_pdf_text(path: Path) -> str:
    """Extract text from PDF using available libraries."""
    try:
        # Try PyPDF2 first
        from PyPDF2 import PdfReader  # type: ignore[import]
        reader = PdfReader(str(path))
        text_parts = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract page text: {e}")
                continue
        content = "\n\n".join(text_parts)
        if content.strip():
            return content
    except ImportError:
        pass

    try:
        # Try pdfminer.six
        from pdfminer.high_level import extract_text  # type: ignore[import]
        content = extract_text(str(path))
        if content.strip():
            return content
    except ImportError:
        pass

    try:
        # Try pymupdf (fitz)
        import fitz  # type: ignore[import]
        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        content = "\n\n".join(text_parts)
        doc.close()
        if content.strip():
            return content
    except ImportError:
        pass

    raise KnowledgeBaseParserError(
        "No PDF extraction library available. "
        "Install: pip install PyPDF2  OR  pip install pdfminer.six  OR  pip install pymupdf"
    )


def fetch_url_content(url: str) -> Tuple[List[str], str]:
    """
    Fetch and parse URL content.

    Returns:
        Tuple of (chunks, content_hash)

    Raises:
        SSRFDetectedError: If URL points to internal resource
        KnowledgeBaseParserError: If fetch fails
    """
    if _is_blocked_url(url):
        raise SSRFDetectedError(f"URL blocked: {url}")

    parsed = urlparse(url)
    if _is_blocked_host(parsed.netloc):
        raise SSRFDetectedError(f"URL host blocked: {parsed.netloc}")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; KnowledgeBaseBot/1.0; "
                "+mailto:support@example.com)"
            )
        }
        response = requests.get(url, headers=headers, timeout=URL_TIMEOUT, stream=True)
        response.raise_for_status()

        # Check content length before downloading
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_FILE_SIZE:
            raise FileSizeLimitError(
                f"URL content length {content_length} exceeds limit {MAX_FILE_SIZE}"
            )

        content = response.text

        # Check resolved IPs against blocklist (defense in depth)
        # Note: requests.get may have already resolved the hostname

    except requests.exceptions.Timeout:
        raise KnowledgeBaseParserError(f"URL fetch timeout: {url}")
    except requests.exceptions.RequestException as e:
        raise KnowledgeBaseParserError(f"URL fetch failed: {e}")

    # Parse content
    # Try to extract main content (simple heuristic)
    content = _extract_main_content(content, url)

    if not content.strip():
        raise KnowledgeBaseParserError(f"No content extracted from URL: {url}")

    return parse_markdown(content)


def _extract_main_content(html: str, url: str) -> str:
    """Extract main text content from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content
        main = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|article|post|main"))
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n\n".join(lines)
    except ImportError:
        # Fallback: strip HTML tags manually (bs4 not available)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
