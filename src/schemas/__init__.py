# -*- coding: utf-8 -*-
"""
===================================
DSA Schemas
===================================

Pydantic schemas for report output validation and internal contracts.
"""

from src.schemas.analysis_context_pack import (
    PACK_VERSION,
    AnalysisContextBlock,
    AnalysisContextItem,
    AnalysisContextPack,
    AnalysisSubject,
    ContextFieldStatus,
    DataQuality,
)
from src.schemas.report_schema import AnalysisReportSchema
from src.schemas.knowledge_base import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeDocumentItem,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentListResponse,
    KnowledgeChunkHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    FileUploadResponse,
    SourceType,
    ValidationStatus,
)

__all__ = [
    # Report schemas
    "AnalysisReportSchema",
    "PACK_VERSION",
    "AnalysisContextBlock",
    "AnalysisContextItem",
    "AnalysisContextPack",
    "AnalysisSubject",
    "ContextFieldStatus",
    "DataQuality",
    # Knowledge base schemas
    "KnowledgeDocumentCreate",
    "KnowledgeDocumentUpdate",
    "KnowledgeDocumentItem",
    "KnowledgeDocumentDetailResponse",
    "KnowledgeDocumentListResponse",
    "KnowledgeChunkHit",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResponse",
    "FileUploadResponse",
    "SourceType",
    "ValidationStatus",
]
