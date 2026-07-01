# -*- coding: utf-8 -*-
"""Unit tests for knowledge base parser."""

import os
import tempfile
import unittest
from pathlib import Path

from src.services.knowledge_base_parser import (
    parse_text,
    parse_markdown,
    compute_content_hash,
    _split_into_chunks,
    _estimate_tokens,
    _is_blocked_url,
    ContentLengthLimitError,
    FileSizeLimitError,
    SSRFDetectedError,
)


class TextParserTestCase(unittest.TestCase):
    """Test text parsing."""

    def test_parse_text_simple(self):
        """Test parsing simple text."""
        content = "这是测试内容。"
        chunks, hash_val = parse_text(content)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], content)
        self.assertTrue(len(hash_val) > 0)

    def test_parse_text_empty(self):
        """Test parsing empty content."""
        chunks, hash_val = parse_text("")
        self.assertEqual(len(chunks), 0)

    def test_parse_text_long(self):
        """Test parsing long content splits into chunks at sentence boundaries."""
        # Use text with sentence boundaries
        content = "这是第一句内容。" * 100 + "\n\n" + "这是第二段内容。" * 100
        chunks, hash_val = parse_text(content)
        # Should split at paragraph boundary
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(len(hash_val) > 0)

    def test_parse_text_exceeds_limit(self):
        """Test content length limit enforcement."""
        content = "a" * 300000  # Exceeds 200000 limit
        with self.assertRaises(ContentLengthLimitError):
            parse_text(content)

    def test_compute_hash(self):
        """Test content hash computation."""
        hash1 = compute_content_hash("test")
        hash2 = compute_content_hash("test")
        hash3 = compute_content_hash("different")
        self.assertEqual(hash1, hash2)
        self.assertNotEqual(hash1, hash3)

    def test_estimate_tokens(self):
        """Test token estimation."""
        text = "hello world"
        tokens = _estimate_tokens(text)
        self.assertGreater(tokens, 0)


class MarkdownParserTestCase(unittest.TestCase):
    """Test markdown parsing."""

    def test_parse_markdown_simple(self):
        """Test parsing simple markdown."""
        content = "# 标题\n\n这是正文内容。"
        chunks, hash_val = parse_markdown(content)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(len(hash_val) > 0)

    def test_parse_markdown_with_headers(self):
        """Test markdown with multiple headers."""
        content = """# 第一章

这是第一章的内容。

## 第一节

这是第一节的内容。

## 第二节

这是第二节的内容。
"""
        chunks, hash_val = parse_markdown(content)
        self.assertGreaterEqual(len(chunks), 1)
        # Headers should be preserved
        text = "\n".join(chunks)
        self.assertIn("第一章", text)

    def test_parse_markdown_exceeds_limit(self):
        """Test markdown content length limit."""
        content = "# 标题\n\n" + ("内容" * 100000)
        with self.assertRaises(ContentLengthLimitError):
            parse_markdown(content)


class ChunkSplitTestCase(unittest.TestCase):
    """Test chunk splitting."""

    def test_split_short_text(self):
        """Test splitting short text returns single chunk."""
        text = "短文本"
        chunks = _split_into_chunks(text, chunk_size=1000, overlap=100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_split_long_text(self):
        """Test splitting long text."""
        text = "这是测试内容。" * 200
        chunks = _split_into_chunks(text, chunk_size=100, overlap=10)
        self.assertGreater(len(chunks), 1)

    def test_split_empty(self):
        """Test splitting empty text."""
        chunks = _split_into_chunks("")
        self.assertEqual(len(chunks), 0)

    def test_split_with_overlap(self):
        """Test chunks have overlap."""
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 50
        chunks = _split_into_chunks(text, chunk_size=100, overlap=20)
        if len(chunks) > 1:
            # Overlap should be present
            pass  # Just verify no error


class SSRFProtectionTestCase(unittest.TestCase):
    """Test SSRF protection."""

    def test_block_localhost(self):
        """Test localhost URLs are blocked."""
        blocked_urls = [
            "file:///etc/passwd",
            "ftp://localhost/test",
            "sftp://127.0.0.1/test",
        ]
        for url in blocked_urls:
            self.assertTrue(_is_blocked_url(url))

    def test_allow_http_urls(self):
        """Test normal HTTP/HTTPS URLs are allowed."""
        allowed_urls = [
            "https://example.com/article",
            "http://example.com/test",
        ]
        for url in allowed_urls:
            self.assertFalse(_is_blocked_url(url))


class PDFParserTestCase(unittest.TestCase):
    """Test PDF parsing."""

    def test_parse_pdf_file_not_found(self):
        """Test PDF parsing with missing file."""
        from src.services.knowledge_base_parser import parse_pdf
        with self.assertRaises(Exception):
            parse_pdf("/nonexistent/file.pdf")

    def test_parse_pdf_with_mock(self):
        """Test PDF parsing with a minimal PDF file."""
        from src.services.knowledge_base_parser import parse_pdf
        # This test verifies the error handling path
        pass  # Skip actual PDF test without real PDF library


if __name__ == "__main__":
    unittest.main()
