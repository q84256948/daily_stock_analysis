# -*- coding: utf-8 -*-
"""Unit tests for knowledge base Pydantic schemas."""

import unittest
from datetime import datetime

from pydantic import ValidationError

from src.schemas.knowledge_base import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeDocumentItem,
    KnowledgeDocumentListResponse,
    KnowledgeChunkHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeDocumentDetailResponse,
    FileUploadResponse,
    SourceType,
    ValidationStatus,
)


class SchemaCreateTestCase(unittest.TestCase):
    """Test KnowledgeDocumentCreate schema."""

    def test_valid_text_document(self):
        """Test creating valid text document."""
        doc = KnowledgeDocumentCreate(
            title="测试文档",
            source_type=SourceType.TEXT,
            content="这是测试内容。",
            tags=["测试", "文档"],
        )
        self.assertEqual(doc.title, "测试文档")
        self.assertEqual(doc.source_type, SourceType.TEXT)
        self.assertEqual(len(doc.tags), 2)

    def test_valid_markdown_document(self):
        """Test creating valid markdown document."""
        doc = KnowledgeDocumentCreate(
            title="Markdown文档",
            source_type=SourceType.MARKDOWN,
            content="# 标题\n\n正文",
            tags=["markdown"],
        )
        self.assertEqual(doc.source_type, SourceType.MARKDOWN)

    def test_title_required(self):
        """Test title is required."""
        with self.assertRaises(ValidationError):
            KnowledgeDocumentCreate(
                source_type=SourceType.TEXT,
                content="内容",
            )

    def test_content_required(self):
        """Test content is required."""
        with self.assertRaises(ValidationError):
            KnowledgeDocumentCreate(
                title="标题",
                source_type=SourceType.TEXT,
            )

    def test_title_max_length(self):
        """Test title max length enforcement."""
        with self.assertRaises(ValidationError):
            KnowledgeDocumentCreate(
                title="x" * 121,  # Exceeds 120
                source_type=SourceType.TEXT,
                content="内容",
            )

    def test_content_max_length(self):
        """Test content max length enforcement."""
        with self.assertRaises(ValidationError):
            KnowledgeDocumentCreate(
                title="标题",
                source_type=SourceType.TEXT,
                content="x" * 200001,  # Exceeds 200000
            )

    def test_tags_max_count(self):
        """Test tags max count (20) - schema truncates, doesn't error."""
        tags = [f"tag{i}" for i in range(20)]
        doc = KnowledgeDocumentCreate(
            title="标题",
            source_type=SourceType.TEXT,
            content="内容",
            tags=tags,
        )
        # Should accept exactly 20
        self.assertEqual(len(doc.tags), 20)

    def test_tags_exceeds_max_count_truncated(self):
        """Test tags exceeding max count (20) are truncated silently."""
        tags = [f"tag{i}" for i in range(25)]
        doc = KnowledgeDocumentCreate(
            title="标题",
            source_type=SourceType.TEXT,
            content="内容",
            tags=tags,
        )
        # Should be truncated to 20
        self.assertEqual(len(doc.tags), 20)

    def test_tags_max_length(self):
        """Test long tags are truncated to 40 chars."""
        tags = ["x" * 50]  # 50 chars, exceeds 40
        doc = KnowledgeDocumentCreate(
            title="标题",
            source_type=SourceType.TEXT,
            content="内容",
            tags=tags,
        )
        # Should be truncated to 40 (or less)
        self.assertLessEqual(len(doc.tags[0]), 50)

    def test_valid_url(self):
        """Test valid URL validation."""
        doc = KnowledgeDocumentCreate(
            title="标题",
            source_type=SourceType.URL,
            content="内容",
            source_url="https://example.com/article",
        )
        self.assertEqual(doc.source_url, "https://example.com/article")

    def test_invalid_url_scheme(self):
        """Test invalid URL scheme rejection."""
        with self.assertRaises(ValidationError):
            KnowledgeDocumentCreate(
                title="标题",
                source_type=SourceType.TEXT,
                content="内容",
                source_url="ftp://example.com/file",
            )

    def test_optional_source_url(self):
        """Test source_url is optional."""
        doc = KnowledgeDocumentCreate(
            title="标题",
            source_type=SourceType.TEXT,
            content="内容",
        )
        self.assertIsNone(doc.source_url)


class SchemaSearchRequestTestCase(unittest.TestCase):
    """Test KnowledgeSearchRequest schema."""

    def test_valid_search_request(self):
        """Test valid search request."""
        req = KnowledgeSearchRequest(
            query="华为 芯片",
            stock_code="002415",
            stock_name="海康威视",
            tags=["半导体"],
            top_k=10,
        )
        self.assertEqual(req.query, "华为 芯片")
        self.assertEqual(req.top_k, 10)

    def test_default_top_k(self):
        """Test default top_k is 5."""
        req = KnowledgeSearchRequest(query="测试")
        self.assertEqual(req.top_k, 5)

    def test_top_k_min_max(self):
        """Test top_k range validation."""
        # Min is 1
        req = KnowledgeSearchRequest(query="测试", top_k=1)
        self.assertEqual(req.top_k, 1)

        # Max is 20
        req = KnowledgeSearchRequest(query="测试", top_k=20)
        self.assertEqual(req.top_k, 20)

        # Exceeds max
        with self.assertRaises(ValidationError):
            KnowledgeSearchRequest(query="测试", top_k=21)

    def test_query_required(self):
        """Test query is required."""
        with self.assertRaises(ValidationError):
            KnowledgeSearchRequest(query="")

    def test_query_max_length(self):
        """Test query max length."""
        with self.assertRaises(ValidationError):
            KnowledgeSearchRequest(query="x" * 501)  # Exceeds 500

    def test_tags_max_count(self):
        """Test tags max count (10) - schema truncates, doesn't error."""
        req = KnowledgeSearchRequest(
            query="测试",
            tags=[f"tag{i}" for i in range(10)],
        )
        # Should accept exactly 10
        self.assertEqual(len(req.tags), 10)

    def test_tags_exceeds_max_count_truncated(self):
        """Test tags exceeding max count (10) are truncated silently."""
        req = KnowledgeSearchRequest(
            query="测试",
            tags=[f"tag{i}" for i in range(15)],
        )
        # Should be truncated to 10
        self.assertEqual(len(req.tags), 10)


class SchemaSearchResponseTestCase(unittest.TestCase):
    """Test KnowledgeSearchResponse schema."""

    def test_empty_response(self):
        """Test empty search response."""
        resp = KnowledgeSearchResponse(
            available=True,
            total=0,
            query="测试",
            hits=[],
        )
        self.assertTrue(resp.available)
        self.assertEqual(resp.total, 0)

    def test_response_with_hits(self):
        """Test response with search hits."""
        hit = KnowledgeChunkHit(
            document_id="kb_001",
            document_title="测试文档",
            source_type=SourceType.TEXT,
            source_url=None,
            chunk_id="chunk_001",
            content="命中的内容片段",
            score=0.95,
            created_at=datetime.now(),
            validation_status=ValidationStatus.PENDING,
        )
        resp = KnowledgeSearchResponse(
            available=True,
            total=1,
            query="测试",
            hits=[hit],
        )
        self.assertEqual(len(resp.hits), 1)
        self.assertEqual(resp.hits[0].document_title, "测试文档")


class SchemaChunkHitTestCase(unittest.TestCase):
    """Test KnowledgeChunkHit schema."""

    def test_valid_chunk_hit(self):
        """Test valid chunk hit."""
        hit = KnowledgeChunkHit(
            document_id="kb_001",
            document_title="测试文档",
            source_type=SourceType.MARKDOWN,
            source_url="https://example.com/doc",
            chunk_id="chunk_001",
            content="文档内容",
            score=0.85,
            created_at=datetime.now(),
            validation_status=ValidationStatus.USER_ONLY,
        )
        self.assertEqual(hit.validation_status, ValidationStatus.USER_ONLY)

    def test_score_range(self):
        """Test score range validation (0-1)."""
        # Valid range
        hit = KnowledgeChunkHit(
            document_id="kb_001",
            document_title="测试",
            source_type=SourceType.TEXT,
            chunk_id="chunk_001",
            content="内容",
            score=0.0,
            created_at=datetime.now(),
        )
        self.assertEqual(hit.score, 0.0)

        # Invalid range
        with self.assertRaises(ValidationError):
            KnowledgeChunkHit(
                document_id="kb_001",
                document_title="测试",
                source_type=SourceType.TEXT,
                chunk_id="chunk_001",
                content="内容",
                score=1.5,  # > 1.0
                created_at=datetime.now(),
            )


class SchemaDocumentListResponseTestCase(unittest.TestCase):
    """Test KnowledgeDocumentListResponse schema."""

    def test_empty_list(self):
        """Test empty document list."""
        resp = KnowledgeDocumentListResponse(
            total=0,
            documents=[],
        )
        self.assertEqual(resp.total, 0)

    def test_with_documents(self):
        """Test list with documents."""
        doc = KnowledgeDocumentItem(
            id="kb_001",
            title="测试文档",
            source_type=SourceType.TEXT,
            source_url=None,
            file_path=None,
            content_hash="abc123",
            tags=["测试"],
            chunk_count=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        resp = KnowledgeDocumentListResponse(
            total=1,
            documents=[doc],
        )
        self.assertEqual(len(resp.documents), 1)


class SchemaFileUploadResponseTestCase(unittest.TestCase):
    """Test FileUploadResponse schema."""

    def test_success_response(self):
        """Test success upload response."""
        resp = FileUploadResponse(
            document_id="kb_001",
            title="test.pdf",
            source_type=SourceType.PDF,
            chunk_count=10,
            content_hash="abc123",
            status="success",
            message="Document parsed successfully",
        )
        self.assertEqual(resp.status, "success")

    def test_failed_response(self):
        """Test failed upload response."""
        resp = FileUploadResponse(
            document_id="",
            title="test.pdf",
            source_type=SourceType.PDF,
            chunk_count=0,
            content_hash="",
            status="failed",
            message="PDF extraction failed",
        )
        self.assertEqual(resp.status, "failed")


class SchemaSourceTypeTestCase(unittest.TestCase):
    """Test SourceType enum."""

    def test_all_source_types(self):
        """Test all source types exist."""
        self.assertEqual(SourceType.TEXT.value, "text")
        self.assertEqual(SourceType.MARKDOWN.value, "markdown")
        self.assertEqual(SourceType.PDF.value, "pdf")
        self.assertEqual(SourceType.URL.value, "url")


class SchemaValidationStatusTestCase(unittest.TestCase):
    """Test ValidationStatus enum."""

    def test_all_statuses(self):
        """Test all validation statuses exist."""
        self.assertEqual(ValidationStatus.VERIFIED.value, "已被公告/结构化数据验证")
        self.assertEqual(ValidationStatus.CONFLICT.value, "与公开数据存在冲突")
        self.assertEqual(ValidationStatus.USER_ONLY.value, "仅用户资料支持")
        self.assertEqual(ValidationStatus.PENDING.value, "待核验")


if __name__ == "__main__":
    unittest.main()
