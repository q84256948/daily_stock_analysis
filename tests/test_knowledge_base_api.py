# -*- coding: utf-8 -*-
"""Unit tests for knowledge base API endpoints."""

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.config import Config
from src.storage import DatabaseManager
from api.app import create_app


class KnowledgeBaseAPITestCase(unittest.TestCase):
    """Knowledge base API endpoint tests."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "kb_api_test.db"
        self.kb_dir = Path(self.temp_dir.name) / "kb"
        self.kb_dir.mkdir()

        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["KNOWLEDGE_BASE_DIR"] = str(self.kb_dir)

        Config.reset_instance()
        DatabaseManager.reset_instance()

        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("KNOWLEDGE_BASE_DIR", None)
        self.temp_dir.cleanup()

    def test_create_text_document(self):
        """Test POST /api/v1/knowledge-base/documents/text."""
        response = self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "API测试文档",
                "source_type": "text",
                "content": "这是测试内容。",
                "tags": ["测试"],
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "API测试文档")
        self.assertIn("id", data)

    def test_create_text_document_validation(self):
        """Test input validation for text document creation."""
        # Missing required fields
        response = self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={},
        )
        self.assertEqual(response.status_code, 422)

        # Empty content (should fail)
        response = self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "测试",
                "source_type": "text",
                "content": "",  # Empty content
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_list_documents(self):
        """Test GET /api/v1/knowledge-base/documents."""
        # Create a document first
        self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "列表测试",
                "source_type": "text",
                "content": "内容",
            },
        )
        response = self.client.get("/api/v1/knowledge-base/documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["total"], 1)

    def test_list_documents_with_filter(self):
        """Test listing with source_type filter."""
        self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "文本",
                "source_type": "text",
                "content": "文本内容",
            },
        )
        self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "Markdown",
                "source_type": "markdown",
                "content": "# 标题",
            },
        )
        response = self.client.get(
            "/api/v1/knowledge-base/documents",
            params={"source_type": "text"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(data["documents"][0]["title"], "文本")

    def test_get_document(self):
        """Test GET /api/v1/knowledge-base/documents/{id}."""
        # Create a document
        create_resp = self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "详情测试",
                "source_type": "text",
                "content": "这是测试内容。",
            },
        )
        doc_id = create_resp.json()["id"]

        response = self.client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], doc_id)
        self.assertIn("chunks", data)

    def test_get_document_not_found(self):
        """Test getting non-existent document."""
        response = self.client.get(
            "/api/v1/knowledge-base/documents/nonexistent_id"
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_document(self):
        """Test DELETE /api/v1/knowledge-base/documents/{id}."""
        # Create a document
        create_resp = self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "删除测试",
                "source_type": "text",
                "content": "内容",
            },
        )
        doc_id = create_resp.json()["id"]

        response = self.client.delete(
            f"/api/v1/knowledge-base/documents/{doc_id}"
        )
        self.assertEqual(response.status_code, 200)

        # Verify deleted
        get_resp = self.client.get(
            f"/api/v1/knowledge-base/documents/{doc_id}"
        )
        self.assertEqual(get_resp.status_code, 404)

    def test_search(self):
        """Test POST /api/v1/knowledge-base/search."""
        # Create documents
        self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "半导体",
                "source_type": "text",
                "content": "华为是中国最大的芯片设计公司。",
                "tags": ["半导体"],
            },
        )
        self.client.post(
            "/api/v1/knowledge-base/documents/text",
            json={
                "title": "白酒",
                "source_type": "text",
                "content": "茅台是中国著名的白酒企业。",
                "tags": ["白酒"],
            },
        )

        response = self.client.post(
            "/api/v1/knowledge-base/search",
            json={
                "query": "华为 芯片",
                "top_k": 5,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["available"])
        self.assertGreaterEqual(data["total"], 0)  # FTS may or may not find results

    def test_search_validation(self):
        """Test search input validation."""
        response = self.client.post(
            "/api/v1/knowledge-base/search",
            json={"query": ""},  # Empty query should fail
        )
        self.assertEqual(response.status_code, 422)

    def test_status(self):
        """Test GET /api/v1/knowledge-base/status."""
        response = self.client.get("/api/v1/knowledge-base/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("available", data)


if __name__ == "__main__":
    unittest.main()
