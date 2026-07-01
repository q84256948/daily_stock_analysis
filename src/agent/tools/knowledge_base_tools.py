# -*- coding: utf-8 -*-
"""
Knowledge Base tools — search and management for the agent.

Tools:
- search_knowledge_base: full-text search across knowledge base documents
"""

import logging
from typing import Any, Optional

from src.agent.tools.registry import ToolParameter, ToolDefinition
from src.schemas.knowledge_base import KnowledgeSearchRequest

logger = logging.getLogger(__name__)


def _handle_search_knowledge_base(
    query: str,
    stock_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    tags: Optional[list[str]] = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Search the knowledge base for relevant documents.

    This tool allows the agent to search user's private documents, research reports,
    industry materials, and interview notes for supplementary evidence in analysis.

    Important:
    - Knowledge base content has lower authority than official announcements and
      structured data.
    - When citing, always include document title, source type, and snippet.
    - Mark citation as "verified" only if confirmed by official sources.
    """
    from src.services.knowledge_base_service import KnowledgeBaseService

    try:
        service = KnowledgeBaseService()
        request = KnowledgeSearchRequest(
            query=query,
            stock_code=stock_code,
            stock_name=stock_name,
            tags=tags or [],
            top_k=min(top_k, 20),
        )
        response = service.search(request)

        if not response.available:
            return {
                "available": False,
                "error": response.message or "Knowledge base unavailable",
                "hits": [],
            }

        if not response.hits:
            return {
                "available": True,
                "total": 0,
                "query": query,
                "message": "No relevant documents found in knowledge base.",
                "hits": [],
            }

        # Format hits for agent consumption
        hits = []
        for hit in response.hits:
            hits.append({
                "document_id": hit.document_id,
                "document_title": hit.document_title,
                "source_type": hit.source_type.value if hasattr(hit.source_type, 'value') else str(hit.source_type),
                "source_url": hit.source_url,
                "chunk_id": hit.chunk_id,
                "snippet": hit.content[:500] + ("..." if len(hit.content) > 500 else ""),
                "relevance_score": round(hit.score, 2),
                "created_at": hit.created_at.isoformat() if hit.created_at else None,
                "validation_status": hit.validation_status.value if hasattr(hit.validation_status, 'value') else str(hit.validation_status),
            })

        return {
            "available": True,
            "total": response.total,
            "query": query,
            "hits": hits,
            "message": f"Found {response.total} relevant document(s). "
                       f"Remember: these are user materials and should be verified "
                       f"against official announcements before making investment decisions.",
        }

    except Exception as e:
        logger.exception("Knowledge base search failed")
        return {
            "available": False,
            "error": str(e),
            "hits": [],
        }


# Tool definition for registration
SEARCH_KNOWLEDGE_BASE_TOOL = ToolDefinition(
    name="search_knowledge_base",
    description=(
        "Search the user's private knowledge base for relevant documents. "
        "Use this to find research reports, industry materials, interview notes, "
        "and other user-uploaded content that can supplement analysis. "
        "IMPORTANT: Knowledge base content has lower authority than official "
        "announcements and structured data. Always verify claims against "
        "official sources before making investment decisions. "
        "When citing, include document title, source type, upload time, "
        "and mark the citation status appropriately."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="Search query text (supports Chinese and English). "
                        "Use specific terms for better results.",
            required=True,
        ),
        ToolParameter(
            name="stock_code",
            type="string",
            description="Filter by stock code (e.g., '600519' for Kweichow Moutai). Optional.",
            required=False,
        ),
        ToolParameter(
            name="stock_name",
            type="string",
            description="Filter by stock name (e.g., '贵州茅台'). Optional.",
            required=False,
        ),
        ToolParameter(
            name="tags",
            type="array",
            description="Filter by tags/labels (e.g., ['半导体', '华为']). Optional.",
            required=False,
        ),
        ToolParameter(
            name="top_k",
            type="integer",
            description="Maximum number of results to return (1-20, default 5).",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_search_knowledge_base,
    category="search",
)


def _handle_list_knowledge_documents(
    source_type: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    List documents in the knowledge base.

    Use this to get an overview of available documents or find specific documents.
    """
    from src.services.knowledge_base_service import KnowledgeBaseService

    try:
        service = KnowledgeBaseService()
        response = service.list_documents(
            source_type=source_type,
            tag=tag,
            limit=min(limit, 100),
            offset=offset,
        )

        docs = []
        for doc in response.documents:
            docs.append({
                "id": doc.id,
                "title": doc.title,
                "source_type": doc.source_type.value if hasattr(doc.source_type, 'value') else str(doc.source_type),
                "source_url": doc.source_url,
                "tags": doc.tags,
                "chunk_count": doc.chunk_count,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            })

        return {
            "available": True,
            "total": response.total,
            "documents": docs,
        }

    except Exception as e:
        logger.exception("Failed to list documents")
        return {
            "available": False,
            "error": str(e),
            "documents": [],
        }


LIST_KNOWLEDGE_DOCUMENTS_TOOL = ToolDefinition(
    name="list_knowledge_documents",
    description=(
        "List documents in the knowledge base. "
        "Use this to get an overview of available documents or find specific documents "
        "by source type or tag."
    ),
    parameters=[
        ToolParameter(
            name="source_type",
            type="string",
            description="Filter by source type: text, markdown, pdf, url. Optional.",
            required=False,
        ),
        ToolParameter(
            name="tag",
            type="string",
            description="Filter by tag/label. Optional.",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of documents to return (1-100, default 20).",
            required=False,
            default=20,
        ),
        ToolParameter(
            name="offset",
            type="integer",
            description="Number of documents to skip for pagination (default 0).",
            required=False,
            default=0,
        ),
    ],
    handler=_handle_list_knowledge_documents,
    category="search",
)
