# -*- coding: utf-8 -*-
"""Unit tests for knowledge base agent tools."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.config import Config
from src.storage import DatabaseManager
from src.agent.tools.knowledge_base_tools import (
    _handle_search_knowledge_base,
    _handle_list_knowledge_documents,
    SEARCH_KNOWLEDGE_BASE_TOOL,
    LIST_KNOWLEDGE_DOCUMENTS_TOOL,
)
from src.services.knowledge_base_service import KnowledgeBaseService
from src.schemas.knowledge_base import KnowledgeSearchResponse


class KnowledgeBaseToolsTestCase(unittest.TestCase):
    """Knowledge base agent tool tests."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "kb_tools_test.db"
        self.kb_dir = Path(self.temp_dir.name) / "kb"
        self.kb_dir.mkdir()

        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["KNOWLEDGE_BASE_DIR"] = str(self.kb_dir)

        Config.reset_instance()
        DatabaseManager.reset_instance()

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("KNOWLEDGE_BASE_DIR", None)
        self.temp_dir.cleanup()

    def test_tool_definitions_exist(self):
        """Test tool definitions are properly defined."""
        self.assertEqual(SEARCH_KNOWLEDGE_BASE_TOOL.name, "search_knowledge_base")
        self.assertEqual(
            LIST_KNOWLEDGE_DOCUMENTS_TOOL.name, "list_knowledge_documents"
        )
        # Check parameters
        param_names = [p.name for p in SEARCH_KNOWLEDGE_BASE_TOOL.parameters]
        self.assertIn("query", param_names)
        self.assertIn("stock_code", param_names)
        self.assertIn("stock_name", param_names)
        self.assertIn("tags", param_names)
        self.assertIn("top_k", param_names)

    def test_search_with_no_results(self):
        """Test search returns empty when no documents."""
        with patch.object(
            KnowledgeBaseService, "search"
        ) as mock_search:
            mock_response = KnowledgeSearchResponse(
                available=True, total=0, query="test", hits=[]
            )
            mock_search.return_value = mock_response

            result = _handle_search_knowledge_base(query="test")

        self.assertTrue(result["available"])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["hits"], [])

    def test_search_with_hits(self):
        """Test search returns formatted hits."""
        from datetime import datetime
        from src.schemas.knowledge_base import (
            KnowledgeChunkHit,
            SourceType,
            ValidationStatus,
        )

        with patch.object(
            KnowledgeBaseService, "search"
        ) as mock_search:
            mock_hit = KnowledgeChunkHit(
                document_id="kb_001",
                document_title="测试文档",
                source_type=SourceType.TEXT,
                source_url=None,
                chunk_id="chunk_001",
                content="这是测试内容。",
                score=0.95,
                created_at=datetime.now(),
                validation_status=ValidationStatus.PENDING,
            )
            mock_response = KnowledgeSearchResponse(
                available=True, total=1, query="测试", hits=[mock_hit]
            )
            mock_search.return_value = mock_response

            result = _handle_search_knowledge_base(query="测试", top_k=5)

        self.assertTrue(result["available"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["hits"]), 1)
        self.assertEqual(result["hits"][0]["document_title"], "测试文档")

    def test_search_when_unavailable(self):
        """Test search handles unavailable service."""
        with patch.object(
            KnowledgeBaseService, "search"
        ) as mock_search:
            mock_response = KnowledgeSearchResponse(
                available=False, total=0, query="test", message="Service unavailable"
            )
            mock_search.return_value = mock_response

            result = _handle_search_knowledge_base(query="test")

        self.assertFalse(result["available"])
        self.assertIn("error", result)

    def test_search_exception_handling(self):
        """Test search handles exceptions gracefully."""
        with patch.object(
            KnowledgeBaseService, "search"
        ) as mock_search:
            mock_search.side_effect = Exception("Database error")

            result = _handle_search_knowledge_base(query="test")

        self.assertFalse(result["available"])
        self.assertIn("error", result)

    def test_list_documents(self):
        """Test list documents returns formatted output."""
        from datetime import datetime
        from src.schemas.knowledge_base import (
            KnowledgeDocumentListResponse,
            KnowledgeDocumentItem,
            SourceType,
        )

        with patch.object(
            KnowledgeBaseService, "list_documents"
        ) as mock_list:
            mock_item = KnowledgeDocumentItem(
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
            mock_response = KnowledgeDocumentListResponse(
                total=1, documents=[mock_item]
            )
            mock_list.return_value = mock_response

            result = _handle_list_knowledge_documents(limit=10)

        self.assertTrue(result["available"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["documents"][0]["title"], "测试文档")

    def test_list_documents_with_filters(self):
        """Test list documents with filters."""
        with patch.object(
            KnowledgeBaseService, "list_documents"
        ) as mock_list:
            from src.schemas.knowledge_base import KnowledgeDocumentListResponse
            mock_response = KnowledgeDocumentListResponse(total=0, documents=[])
            mock_list.return_value = mock_response

            result = _handle_list_knowledge_documents(
                source_type="text", tag="半导体", limit=20, offset=0
            )

        # Verify filters were passed
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args
        self.assertEqual(call_kwargs.kwargs.get("source_type"), "text")
        self.assertEqual(call_kwargs.kwargs.get("tag"), "半导体")

    def test_list_documents_exception_handling(self):
        """Test list documents handles exceptions."""
        with patch.object(
            KnowledgeBaseService, "list_documents"
        ) as mock_list:
            mock_list.side_effect = Exception("Database error")

            result = _handle_list_knowledge_documents()

        self.assertFalse(result["available"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
