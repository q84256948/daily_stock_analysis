# -*- coding: utf-8 -*-
"""
===================================
Knowledge Base Service
===================================

Business logic for knowledge base document management and search.
Uses SQLite FTS5 for full-text search.

Features:
- Document CRUD (Create, Read, List, Delete)
- Full-text search with filtering
- SSRF protection for URL fetching
- Chunk-based indexing for long documents
"""

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text, select, func, and_, delete
from sqlalchemy.orm import Session

from src.storage import DatabaseManager, KnowledgeDocument, KnowledgeChunk
from src.schemas.knowledge_base import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentItem,
    KnowledgeChunkHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    SourceType,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

# Configuration
KB_DIR = os.environ.get("KNOWLEDGE_BASE_DIR", "data/knowledge_base")
MAX_FILE_SIZE = int(os.environ.get("KNOWLEDGE_BASE_MAX_FILE_MB", "20")) * 1024 * 1024


class KnowledgeBaseServiceError(Exception):
    """Base exception for service errors."""
    pass


class DocumentNotFoundError(KnowledgeBaseServiceError):
    """Raised when document is not found."""
    pass


class DuplicateDocumentError(KnowledgeBaseServiceError):
    """Raised when document content hash already exists."""
    pass


class KnowledgeBaseService:
    """Service for knowledge base operations."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db = db_manager or DatabaseManager.get_instance()
        self._kb_dir = Path(KB_DIR)
        self._kb_dir.mkdir(parents=True, exist_ok=True)

    # =====================================================================
    # Document Management
    # =====================================================================

    def create_document(
        self,
        request: KnowledgeDocumentCreate,
    ) -> KnowledgeDocumentItem:
        """Create a new knowledge document with chunks."""
        from src.services.knowledge_base_parser import (
            parse_text,
            parse_markdown,
            compute_content_hash,
        )

        # Parse content based on source type
        if request.source_type == SourceType.MARKDOWN:
            chunks, content_hash = parse_markdown(request.content)
        else:
            chunks, content_hash = parse_text(request.content)

        # Check for duplicate
        existing = self._get_by_hash(content_hash)
        if existing:
            raise DuplicateDocumentError(
                f"Document with same content already exists: {existing.id}"
            )

        # Generate document ID
        doc_id = self._generate_doc_id()

        # Save content to file if needed
        file_path = None
        if request.source_type in (SourceType.PDF, SourceType.MARKDOWN):
            file_path = self._save_content(doc_id, request.content, request.source_type)

        # Create document and get values
        item = self._create_doc_record(
            doc_id=doc_id,
            title=request.title,
            source_type=request.source_type.value,
            source_url=request.source_url,
            file_path=file_path,
            content_hash=content_hash,
            tags=request.tags,
            chunk_count=len(chunks),
        )

        # Create chunks
        self._create_chunks(doc_id, chunks)

        # Update FTS index
        self._index_chunks(doc_id, chunks)

        return item

    def create_document_from_file(
        self,
        file_path: str,
        title: str,
        source_type: SourceType,
        tags: Optional[List[str]] = None,
        source_url: Optional[str] = None,
    ) -> KnowledgeDocumentItem:
        """Create document from uploaded file."""
        from src.services.knowledge_base_parser import (
            parse_pdf,
            parse_markdown,
            compute_content_hash,
        )

        path = Path(file_path)
        if not path.exists():
            raise KnowledgeBaseServiceError(f"File not found: {file_path}")

        if path.stat().st_size > MAX_FILE_SIZE:
            raise KnowledgeBaseServiceError(
                f"File size exceeds limit: {path.stat().st_size} > {MAX_FILE_SIZE}"
            )

        # Read and parse content
        content = path.read_text(encoding="utf-8", errors="replace")
        if source_type == SourceType.PDF:
            chunks, content_hash = parse_pdf(file_path)
        else:
            chunks, content_hash = parse_markdown(content)

        # Check for duplicate
        existing = self._get_by_hash(content_hash)
        if existing:
            raise DuplicateDocumentError(
                f"Document with same content already exists: {existing.id}"
            )

        doc_id = self._generate_doc_id()

        # Save content
        file_path_saved = self._save_content(doc_id, content, source_type)

        # Create document (returns item directly)
        item = self._create_doc_record(
            doc_id=doc_id,
            title=title or path.stem,
            source_type=source_type.value,
            source_url=source_url,
            file_path=file_path_saved,
            content_hash=content_hash,
            tags=tags or [],
            chunk_count=len(chunks),
        )

        # Create chunks
        self._create_chunks(doc_id, chunks)

        # Update FTS index
        self._index_chunks(doc_id, chunks)

        return item

    def create_document_from_url(
        self,
        url: str,
        title: str,
        tags: Optional[List[str]] = None,
    ) -> Tuple[KnowledgeDocumentItem, bool]:
        """
        Create document from URL.

        Returns:
            Tuple of (document_item, content_fetched)
            content_fetched is False if only URL was saved (fetch failed)
        """
        from src.services.knowledge_base_parser import (
            fetch_url_content,
            compute_content_hash,
            SSRFDetectedError,
            KnowledgeBaseParserError,
        )

        try:
            chunks, content_hash = fetch_url_content(url)
            content_fetched = True
        except SSRFDetectedError:
            raise
        except KnowledgeBaseParserError as e:
            logger.warning(f"URL fetch failed, saving URL only: {e}")
            # Save URL only with empty content
            chunks = []
            content_hash = compute_content_hash("")
            content_fetched = False

        # Check for duplicate
        existing = self._get_by_hash(content_hash)
        if existing:
            raise DuplicateDocumentError(
                f"Document with same content already exists: {existing.id}"
            )

        doc_id = self._generate_doc_id()

        # Create document (returns item directly)
        item = self._create_doc_record(
            doc_id=doc_id,
            title=title or url,
            source_type=SourceType.URL.value,
            source_url=url,
            file_path=None,
            content_hash=content_hash,
            tags=tags or [],
            chunk_count=len(chunks),
        )

        # Create chunks if content was fetched
        if chunks:
            self._create_chunks(doc_id, chunks)
            self._index_chunks(doc_id, chunks)

        return item, content_fetched

    def list_documents(
        self,
        source_type: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> KnowledgeDocumentListResponse:
        """List documents with optional filtering."""
        with self._db.get_session() as session:
            query = select(KnowledgeDocument).where(
                KnowledgeDocument.deleted_at.is_(None)
            )

            if source_type:
                query = query.where(KnowledgeDocument.source_type == source_type)

            # Count total
            total = session.execute(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.deleted_at.is_(None)
                )
            ).scalar() or 0

            # Apply tag filter in Python (JSON stored)
            query = query.order_by(desc(KnowledgeDocument.created_at))
            query = query.offset(offset).limit(limit)

            docs = session.execute(query).scalars().all()

            items = []
            for doc in docs:
                if tag:
                    # Filter by tag in Python
                    tags = self._parse_tags(doc.tags)
                    if tag not in tags:
                        continue
                items.append(self._doc_to_item(doc, session))

            return KnowledgeDocumentListResponse(
                total=total,
                documents=items,
            )

    def get_document(self, doc_id: str) -> KnowledgeDocumentDetailResponse:
        """Get document detail with chunks."""
        with self._db.get_session() as session:
            doc = session.execute(
                select(KnowledgeDocument).where(
                    and_(
                        KnowledgeDocument.id == doc_id,
                        KnowledgeDocument.deleted_at.is_(None),
                    )
                )
            ).scalars().first()

            if not doc:
                raise DocumentNotFoundError(f"Document not found: {doc_id}")

            # Get chunks
            chunks = session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == doc_id)
                .order_by(KnowledgeChunk.chunk_index)
            ).scalars().all()

            chunk_list = []
            for chunk in chunks:
                metadata = {}
                if chunk.metadata_json:
                    try:
                        metadata = json.loads(chunk.metadata_json)
                    except Exception:
                        pass
                chunk_list.append({
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_estimate": chunk.token_estimate,
                    "metadata": metadata,
                })

            return KnowledgeDocumentDetailResponse(
                id=doc.id,
                title=doc.title,
                source_type=SourceType(doc.source_type),
                source_url=doc.source_url,
                file_path=doc.file_path,
                content_hash=doc.content_hash,
                tags=self._parse_tags(doc.tags),
                chunks=chunk_list,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )

    def delete_document(self, doc_id: str) -> bool:
        """Soft delete document and its chunks."""
        def _write(session: Session) -> bool:
            doc = session.execute(
                select(KnowledgeDocument).where(
                    and_(
                        KnowledgeDocument.id == doc_id,
                        KnowledgeDocument.deleted_at.is_(None),
                    )
                )
            ).scalars().first()

            if not doc:
                return False

            # Soft delete document
            doc.deleted_at = datetime.now()

            # Delete chunks from FTS
            self._delete_fts_chunks(doc_id)

            # Delete chunks from table
            session.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == doc_id
                )
            )

            # Delete file if exists
            if doc.file_path:
                try:
                    Path(doc.file_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to delete file {doc.file_path}: {e}")

            return True

        try:
            return self._db._run_write_transaction(f"delete_doc[{doc_id}]", _write)
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def reindex_document(self, doc_id: str) -> bool:
        """Re-index document chunks."""
        from src.services.knowledge_base_parser import parse_markdown, parse_text

        with self._db.get_session() as session:
            doc = session.execute(
                select(KnowledgeDocument).where(
                    and_(
                        KnowledgeDocument.id == doc_id,
                        KnowledgeDocument.deleted_at.is_(None),
                    )
                )
            ).scalars().first()

            if not doc:
                raise DocumentNotFoundError(f"Document not found: {doc_id}")

            # Read content from file or use source_url
            content = ""
            if doc.file_path and Path(doc.file_path).exists():
                content = Path(doc.file_path).read_text(encoding="utf-8", errors="replace")
            elif doc.source_url:
                from src.services.knowledge_base_parser import fetch_url_content
                try:
                    chunks, _ = fetch_url_content(doc.source_url)
                    content = "\n\n".join(chunks)
                except Exception as e:
                    logger.warning(f"Failed to re-fetch URL: {e}")
                    return False

            if not content:
                logger.warning(f"No content available for reindex: {doc_id}")
                return False

            # Parse content
            if doc.source_type == SourceType.MARKDOWN.value:
                chunks, _ = parse_markdown(content)
            else:
                chunks, _ = parse_text(content)

            # Delete old FTS
            self._delete_fts_chunks(doc_id)

            # Delete old chunks
            session.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == doc_id
                )
            )

            # Create new chunks
            self._create_chunks(doc_id, chunks)

            # Update FTS
            self._index_chunks(doc_id, chunks)

            # Update chunk count
            doc.chunk_count = len(chunks)
            doc.updated_at = datetime.now()

            return True

    # =====================================================================
    # Search
    # =====================================================================

    def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        """
        Full-text search with filtering.
        """
        if not self._db._engine:
            return KnowledgeSearchResponse(
                available=False,
                total=0,
                query=request.query,
                hits=[],
                message="Database not available",
            )

        try:
            # Prepare FTS query
            fts_query = self._prepare_fts_query(request.query)

            # Build SQL with optional filters
            params: Dict[str, Any] = {"query": fts_query, "limit": request.top_k}

            # Build the search SQL
            sql = text("""
                SELECT
                    kc.id as chunk_id,
                    kc.document_id,
                    kc.chunk_index,
                    kc.content,
                    kd.title,
                    kd.source_type,
                    kd.source_url,
                    kd.tags,
                    kd.created_at,
                    kd.updated_at,
                    bm25(knowledge_chunks_fts) as rank
                FROM knowledge_chunks_fts fts
                JOIN knowledge_chunks kc ON kc.id = fts.chunk_id
                JOIN knowledge_documents kd ON kd.id = kc.document_id
                WHERE knowledge_chunks_fts MATCH :query
                  AND kd.deleted_at IS NULL
            """)

            # Execute search
            with self._db._engine.connect() as conn:
                results = conn.execute(sql, params).fetchall()

            # Apply post-filtering and scoring
            hits = []
            for row in results:
                # Parse tags
                tags = []
                if row.tags:
                    try:
                        tags = json.loads(row.tags)
                    except Exception:
                        pass

                # Filter by stock code/name in tags or content
                if request.stock_code:
                    content_lower = row.content.lower()
                    code_lower = request.stock_code.lower()
                    if code_lower not in content_lower and code_lower not in " ".join(tags).lower():
                        continue

                if request.stock_name:
                    content_lower = row.content.lower()
                    name_lower = request.stock_name.lower()
                    if name_lower not in content_lower and name_lower not in " ".join(tags).lower():
                        continue

                # Filter by tags
                if request.tags:
                    if not any(t in tags for t in request.tags):
                        continue

                # Calculate score (BM25 + recency boost)
                score = row.rank if row.rank else 0.5
                # Recency boost: newer docs get slightly higher score
                if row.updated_at:
                    days_old = (datetime.now() - row.updated_at).days
                    recency_boost = max(0, 0.1 - days_old * 0.001)
                    score = score * (1 + recency_boost)

                hits.append(KnowledgeChunkHit(
                    document_id=row.document_id,
                    document_title=row.title,
                    source_type=SourceType(row.source_type),
                    source_url=row.source_url,
                    chunk_id=row.chunk_id,
                    content=row.content,
                    score=min(1.0, max(0.0, -score / 10)),  # Normalize BM25 to 0-1
                    created_at=row.created_at,
                    validation_status=ValidationStatus.PENDING,
                ))

            # Sort by score and limit
            hits.sort(key=lambda h: h.score, reverse=True)
            hits = hits[:request.top_k]

            return KnowledgeSearchResponse(
                available=True,
                total=len(hits),
                query=request.query,
                hits=hits,
                message=None,
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return KnowledgeSearchResponse(
                available=False,
                total=0,
                query=request.query,
                hits=[],
                message=f"Search failed: {str(e)}",
            )

    def _prepare_fts_query(self, query: str) -> str:
        """Prepare query for FTS5 (handle special chars, support Chinese)."""
        # FTS5 query syntax: terms separated by space are AND
        # Support quoted phrases
        import re

        query = query.strip()
        if not query:
            return '""'

        # Escape special FTS5 characters
        special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+", "~"]
        for char in special_chars:
            query = query.replace(char, " ")

        # Split into terms and rephrase for Chinese/English
        terms = query.split()
        if len(terms) == 1:
            return f'"{terms[0]}"' if terms[0] else '""'

        # Use AND for multiple terms
        return " ".join(f'"{t}"' for t in terms if t)

    # =====================================================================
    # Helper Methods
    # =====================================================================

    def _generate_doc_id(self) -> str:
        """Generate unique document ID."""
        now = datetime.now()
        random_suffix = os.urandom(4).hex()
        return f"kb_{now.strftime('%Y%m%d%H%M%S')}_{random_suffix}"

    def _get_by_hash(self, content_hash: str) -> Optional[KnowledgeDocument]:
        """Find document by content hash."""
        with self._db.get_session() as session:
            return session.execute(
                select(KnowledgeDocument).where(
                    and_(
                        KnowledgeDocument.content_hash == content_hash,
                        KnowledgeDocument.deleted_at.is_(None),
                    )
                )
            ).scalars().first()

    def _create_doc_record(
        self,
        doc_id: str,
        title: str,
        source_type: str,
        source_url: Optional[str],
        file_path: Optional[str],
        content_hash: str,
        tags: List[str],
        chunk_count: int,
    ) -> KnowledgeDocumentItem:
        """Create document record in DB and return as item."""
        def _write(session: Session) -> KnowledgeDocumentItem:
            doc = KnowledgeDocument(
                id=doc_id,
                title=title,
                source_type=source_type,
                source_url=source_url,
                file_path=file_path,
                content_hash=content_hash,
                tags=json.dumps(tags, ensure_ascii=False),
                chunk_count=chunk_count,
            )
            session.add(doc)
            session.flush()
            # Return item directly while session is still active
            return KnowledgeDocumentItem(
                id=doc.id,
                title=doc.title,
                source_type=SourceType(doc.source_type),
                source_url=doc.source_url,
                file_path=doc.file_path,
                content_hash=doc.content_hash,
                tags=self._parse_tags(doc.tags),
                chunk_count=doc.chunk_count,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )

        return self._db._run_write_transaction(f"create_doc[{doc_id}]", _write)

    def _create_chunks(self, doc_id: str, chunks: List[str]) -> None:
        """Create chunk records in DB."""
        def _write(session: Session) -> None:
            for idx, content in enumerate(chunks):
                from src.services.knowledge_base_parser import _estimate_tokens
                chunk_id = f"{doc_id}_chunk_{idx:04d}"
                chunk = KnowledgeChunk(
                    id=chunk_id,
                    document_id=doc_id,
                    chunk_index=idx,
                    content=content,
                    token_estimate=_estimate_tokens(content),
                )
                session.add(chunk)

        self._db._run_write_transaction(f"create_chunks[{doc_id}]", _write)

    def _index_chunks(self, doc_id: str, chunks: List[str]) -> None:
        """Index chunks in FTS5 table."""
        if not self._db._engine:
            return

        try:
            with self._db._engine.connect() as conn:
                for idx, content in enumerate(chunks):
                    chunk_id = f"{doc_id}_chunk_{idx:04d}"
                    conn.execute(
                        text("""
                            INSERT INTO knowledge_chunks_fts (content, document_id, chunk_id)
                            VALUES (:content, :document_id, :chunk_id)
                        """),
                        {"content": content, "document_id": doc_id, "chunk_id": chunk_id},
                    )
        except Exception as e:
            logger.error(f"Failed to index chunks for {doc_id}: {e}")

    def _delete_fts_chunks(self, doc_id: str) -> None:
        """Delete chunks from FTS5 table."""
        if not self._db._engine:
            return

        try:
            with self._db._engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM knowledge_chunks_fts WHERE document_id = :doc_id"),
                    {"doc_id": doc_id},
                )
        except Exception as e:
            logger.error(f"Failed to delete FTS chunks for {doc_id}: {e}")

    def _save_content(
        self,
        doc_id: str,
        content: str,
        source_type: SourceType,
    ) -> str:
        """Save content to file."""
        ext_map = {
            SourceType.MARKDOWN: ".md",
            SourceType.PDF: ".pdf",
            SourceType.TEXT: ".txt",
        }
        ext = ext_map.get(source_type, ".txt")
        file_path = self._kb_dir / f"{doc_id}{ext}"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _parse_tags(self, tags_json: Optional[str]) -> List[str]:
        """Parse tags from JSON."""
        if not tags_json:
            return []
        try:
            return json.loads(tags_json)
        except Exception:
            return []

    def _doc_to_item(
        self,
        doc: KnowledgeDocument,
        session: Optional[Session] = None,
    ) -> KnowledgeDocumentItem:
        """Convert document to response item."""
        # Get values while still attached to session
        source_type_str = str(doc.source_type)
        # Strip any prefix like "SourceType."
        if "." in source_type_str:
            source_type_str = source_type_str.split(".")[-1]

        return KnowledgeDocumentItem(
            id=str(doc.id),  # Force evaluation before session closes
            title=str(doc.title),
            source_type=SourceType(source_type_str.lower()),
            source_url=doc.source_url,
            file_path=doc.file_path,
            content_hash=str(doc.content_hash),
            tags=self._parse_tags(doc.tags),
            chunk_count=int(doc.chunk_count),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


# Need to import for desc
from sqlalchemy import desc
