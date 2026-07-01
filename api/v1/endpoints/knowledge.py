# -*- coding: utf-8 -*-
"""
===================================
Knowledge Base API Endpoints
===================================

REST API for knowledge base document management and search.
"""

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from typing import Annotated

from api.v1.errors import api_error
from src.schemas.knowledge_base import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentItem,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    SourceType,
    FileUploadResponse,
)
from src.services.knowledge_base_service import (
    KnowledgeBaseService,
    DocumentNotFoundError,
    DuplicateDocumentError,
)
from src.services.knowledge_base_parser import (
    SSRFDetectedError,
    FileSizeLimitError,
    ContentLengthLimitError,
    KnowledgeBaseParserError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_kb_service() -> KnowledgeBaseService:
    """Dependency to get KB service instance."""
    return KnowledgeBaseService()


# =====================================================================
# Document Endpoints
# =====================================================================


@router.post(
    "/documents/text",
    response_model=KnowledgeDocumentItem,
    tags=["KnowledgeBase"],
    summary="Create text/markdown document",
    description="Create a new text or markdown document in the knowledge base.",
)
async def create_text_document(
    request: KnowledgeDocumentCreate,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeDocumentItem:
    """Create a new text or markdown document."""
    try:
        return service.create_document(request)
    except DuplicateDocumentError as e:
        raise api_error(409, "DUPLICATE", str(e))
    except KnowledgeBaseParserError as e:
        raise api_error(400, "PARSE_ERROR", str(e))
    except Exception as e:
        logger.exception("Failed to create document")
        raise api_error(500, "INTERNAL", str(e))


@router.post(
    "/documents/upload",
    response_model=FileUploadResponse,
    tags=["KnowledgeBase"],
    summary="Upload file",
    description="Upload a PDF or Markdown file to the knowledge base.",
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload (PDF, Markdown, or text)"),
    title: Optional[str] = Form(None, description="Document title (defaults to filename)"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> FileUploadResponse:
    """Upload and parse a file into the knowledge base."""
    # Determine file type
    filename = file.filename or "unknown"
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    if ext == "pdf":
        source_type = SourceType.PDF
    elif ext in ("md", "markdown"):
        source_type = SourceType.MARKDOWN
    elif ext in ("txt", "text"):
        source_type = SourceType.TEXT
    else:
        # Try to detect from content type
        content_type = file.content_type or ""
        if "pdf" in content_type:
            source_type = SourceType.PDF
        elif "markdown" in content_type:
            source_type = SourceType.MARKDOWN
        elif "text" in content_type:
            source_type = SourceType.TEXT
        else:
            source_type = SourceType.TEXT

    # Parse tags
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Save uploaded file to temp
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f".{ext}" if ext else "",
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Check size
        size = os.path.getsize(tmp_path)
        max_size = int(os.environ.get("KNOWLEDGE_BASE_MAX_FILE_MB", "20")) * 1024 * 1024
        if size > max_size:
            raise api_error(413, "FILE_TOO_LARGE", f"File size {size} exceeds limit {max_size}")

        # Create document
        item = service.create_document_from_file(
            file_path=tmp_path,
            title=title or filename,
            source_type=source_type,
            tags=tag_list,
        )

        return FileUploadResponse(
            document_id=item.id,
            title=item.title,
            source_type=item.source_type,
            chunk_count=item.chunk_count,
            content_hash=item.content_hash,
            status="success",
            message=f"Document parsed into {item.chunk_count} chunks",
        )
    except KnowledgeBaseParserError as e:
        return FileUploadResponse(
            document_id="",
            title=title or filename,
            source_type=source_type,
            chunk_count=0,
            content_hash="",
            status="failed",
            message=str(e),
        )
    except DuplicateDocumentError as e:
        raise api_error(409, "DUPLICATE", str(e))
    except Exception as e:
        logger.exception("Failed to upload file")
        raise api_error(500, "INTERNAL", str(e))
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post(
    "/documents/url",
    response_model=FileUploadResponse,
    tags=["KnowledgeBase"],
    summary="Create document from URL",
    description="Fetch content from a URL and create a knowledge base document.",
)
async def create_url_document(
    url: str = Query(..., description="URL to fetch content from"),
    title: Optional[str] = Query(None, description="Document title"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> FileUploadResponse:
    """Fetch URL and create document."""
    # Parse tags
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        item, content_fetched = service.create_document_from_url(
            url=url,
            title=title or url,
            tags=tag_list,
        )

        status = "success" if content_fetched else "partial"
        message = (
            f"Document created, content {'fetched' if content_fetched else 'NOT fetched'}"
        )

        return FileUploadResponse(
            document_id=item.id,
            title=item.title,
            source_type=item.source_type,
            chunk_count=item.chunk_count,
            content_hash=item.content_hash,
            status=status,
            message=message,
        )
    except SSRFDetectedError as e:
        raise api_error(400, "SSRF_BLOCKED", str(e))
    except DuplicateDocumentError as e:
        raise api_error(409, "DUPLICATE", str(e))
    except KnowledgeBaseParserError as e:
        return FileUploadResponse(
            document_id="",
            title=title or url,
            source_type=SourceType.URL,
            chunk_count=0,
            content_hash="",
            status="failed",
            message=f"URL fetch failed: {e}",
        )
    except Exception as e:
        logger.exception("Failed to create URL document")
        raise api_error(500, "INTERNAL", str(e))


@router.get(
    "/documents",
    response_model=KnowledgeDocumentListResponse,
    tags=["KnowledgeBase"],
    summary="List documents",
    description="List knowledge base documents with optional filtering.",
)
async def list_documents(
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Skip count"),
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeDocumentListResponse:
    """List documents with optional filtering."""
    try:
        return service.list_documents(
            source_type=source_type,
            tag=tag,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("Failed to list documents")
        raise api_error(500, "INTERNAL", str(e))


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentDetailResponse,
    tags=["KnowledgeBase"],
    summary="Get document detail",
    description="Get document metadata and chunks.",
)
async def get_document(
    document_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeDocumentDetailResponse:
    """Get document detail."""
    try:
        return service.get_document(document_id)
    except DocumentNotFoundError:
        raise api_error(404, "NOT_FOUND", f"Document not found: {document_id}")
    except Exception as e:
        logger.exception("Failed to get document")
        raise api_error(500, "INTERNAL", str(e))


@router.delete(
    "/documents/{document_id}",
    response_model=dict[str, bool | str],
    tags=["KnowledgeBase"],
    summary="Delete document",
    description="Soft delete a document and its chunks.",
)
async def delete_document(
    document_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> dict[str, bool | str]:
    """Delete document."""
    try:
        success = service.delete_document(document_id)
        if success:
            return {"success": True, "message": "Document deleted"}
        else:
            raise api_error(404, "NOT_FOUND", f"Document not found: {document_id}")
    except DocumentNotFoundError:
        raise api_error(404, "NOT_FOUND", f"Document not found: {document_id}")
    except Exception as e:
        logger.exception("Failed to delete document")
        raise api_error(500, "INTERNAL", str(e))


@router.post(
    "/documents/{document_id}/reindex",
    response_model=dict[str, bool | str],
    tags=["KnowledgeBase"],
    summary="Reindex document",
    description="Re-parse and re-index document chunks.",
)
async def reindex_document(
    document_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> dict[str, bool | str]:
    """Re-index document."""
    try:
        success = service.reindex_document(document_id)
        if success:
            return {"success": True, "message": "Document re-indexed"}
        else:
            raise api_error(404, "NOT_FOUND", f"Document not found: {document_id}")
    except DocumentNotFoundError:
        raise api_error(404, "NOT_FOUND", f"Document not found: {document_id}")
    except Exception as e:
        logger.exception("Failed to reindex document")
        raise api_error(500, "INTERNAL", str(e))


# =====================================================================
# Search Endpoint
# =====================================================================


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    tags=["KnowledgeBase"],
    summary="Search knowledge base",
    description="Full-text search across knowledge base documents.",
)
async def search_knowledge_base(
    request: KnowledgeSearchRequest,
    service: KnowledgeBaseService = Depends(get_kb_service),
) -> KnowledgeSearchResponse:
    """Search knowledge base."""
    try:
        return service.search(request)
    except Exception as e:
        logger.exception("Search failed")
        return KnowledgeSearchResponse(
            available=False,
            total=0,
            query=request.query,
            hits=[],
            message=f"Search failed: {str(e)}",
        )


# =====================================================================
# Health Check
# =====================================================================


@router.get(
    "/status",
    response_model=dict[str, bool | int | str],
    tags=["KnowledgeBase"],
    summary="Knowledge base status",
    description="Check if knowledge base is available.",
)
async def get_status() -> dict[str, bool | int | str]:
    """Get knowledge base status."""
    try:
        service = KnowledgeBaseService()
        result = service.list_documents(limit=1)
        return {
            "available": result.total >= 0,  # If query succeeds, it's available
            "document_count": result.total,
        }
    except Exception as e:
        return {
            "available": False,
            "document_count": 0,
            "error": str(e),
        }
