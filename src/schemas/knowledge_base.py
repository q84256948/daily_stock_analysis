# -*- coding: utf-8 -*-
"""
===================================
Knowledge Base - Pydantic Schemas
===================================

Pydantic v2 schemas for knowledge base API requests and responses.
Follows the "类型-契约-数据三层防御" pattern.

Document Types:
- text: Plain text input
- markdown: Markdown content
- pdf: PDF file (text extracted)
- url: Web URL content
"""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceType(str, Enum):
    """Document source types."""

    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    URL = "url"


class ValidationStatus(str, Enum):
    """Knowledge citation validation status."""

    VERIFIED = "已被公告/结构化数据验证"
    CONFLICT = "与公开数据存在冲突"
    USER_ONLY = "仅用户资料支持"
    PENDING = "待核验"


class KnowledgeDocumentCreate(BaseModel):
    """
    Request schema for creating a knowledge document.
    Used for text/markdown input.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "title": "华为产业链深度报告",
                "source_type": "markdown",
                "content": "# 华为产业链分析\n\n...",
                "tags": ["华为", "半导体", "国产替代"],
                "source_url": None,
            }
        },
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="文档标题，1-120字符",
    )
    source_type: SourceType = Field(
        ...,
        description="文档来源类型",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=200000,
        description="文档内容，1-200000字符",
    )
    source_url: Optional[str] = Field(
        None,
        max_length=2048,
        description="原始URL来源，可为空",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="标签列表，最多20个，每项1-40字符",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags_list(cls, v: List[str]) -> List[str]:
        """Validate and truncate tags list."""
        if not v:
            return []
        result = []
        for tag in v:
            if len(tag) > 40:
                tag = tag[:40]  # Truncate long tags
            if tag.strip():
                result.append(tag.strip())
        return result[:20]  # Limit to 20 tags

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL scheme."""
        if v is None:
            return v
        lower = v.lower().strip()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class KnowledgeDocumentUpdate(BaseModel):
    """Request schema for updating tags."""

    tags: List[str] = Field(
        default_factory=list,
        description="标签列表，最多20个，每项1-40字符",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags_list(cls, v: List[str]) -> List[str]:
        """Validate and truncate tags list."""
        if not v:
            return []
        result = []
        for tag in v:
            if len(tag) > 40:
                tag = tag[:40]  # Truncate long tags
            if tag.strip():
                result.append(tag.strip())
        return result[:20]  # Limit to 20 tags


class KnowledgeDocumentItem(BaseModel):
    """
    Response schema for a knowledge document.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "kb_20240101120000_001",
                "title": "华为产业链深度报告",
                "source_type": "markdown",
                "source_url": None,
                "file_path": "/data/kb/kb_20240101120000_001.md",
                "content_hash": "a1b2c3d4e5f6",
                "tags": ["华为", "半导体", "国产替代"],
                "chunk_count": 5,
                "created_at": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:00:00",
            }
        },
    )

    id: str = Field(..., description="文档ID，格式 kb_YYYYMMDDHHMMSS_x")
    title: str = Field(..., description="文档标题")
    source_type: SourceType = Field(..., description="文档来源类型")
    source_url: Optional[str] = Field(None, description="URL来源")
    file_path: Optional[str] = Field(None, description="本地文件路径")
    content_hash: str = Field(..., description="内容hash，用于去重")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    chunk_count: int = Field(0, ge=0, description="chunk数量")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class KnowledgeChunkHit(BaseModel):
    """
    Response schema for a search hit (chunk).
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "document_id": "kb_20240101120000_001",
                "document_title": "华为产业链深度报告",
                "source_type": "markdown",
                "source_url": None,
                "chunk_id": "chunk_001",
                "content": "华为是中国最大的芯片设计公司...",
                "score": 0.95,
                "created_at": "2024-01-01T12:00:00",
                "validation_status": "待核验",
            }
        },
    )

    document_id: str = Field(..., description="所属文档ID")
    document_title: str = Field(..., description="文档标题")
    source_type: SourceType = Field(..., description="文档来源类型")
    source_url: Optional[str] = Field(None, description="URL来源")
    chunk_id: str = Field(..., description="chunk ID")
    content: str = Field(..., description="命中文档片段")
    score: float = Field(..., ge=0.0, le=1.0, description="相关性得分")
    created_at: datetime = Field(..., description="文档创建时间")
    validation_status: ValidationStatus = Field(
        ValidationStatus.PENDING,
        description="校验状态",
    )


class KnowledgeSearchRequest(BaseModel):
    """
    Request schema for knowledge base search.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "query": "华为芯片供应链",
                "stock_code": "002415",
                "stock_name": "海康威视",
                "tags": ["半导体"],
                "top_k": 5,
            }
        },
    )

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="检索query，1-500字符",
    )
    stock_code: Optional[str] = Field(
        None,
        max_length=20,
        description="限定股票代码，可为空",
    )
    stock_name: Optional[str] = Field(
        None,
        max_length=40,
        description="限定股票名称，可为空",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="限定标签，最多10个",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="返回结果数量，1-20",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags_list(cls, v: List[str]) -> List[str]:
        """Validate and truncate tags list."""
        if not v:
            return []
        result = []
        for tag in v:
            if tag.strip():
                result.append(tag.strip())
        return result[:10]  # Limit to 10 tags


class KnowledgeSearchResponse(BaseModel):
    """
    Response schema for knowledge base search.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "available": True,
                "total": 2,
                "query": "华为芯片供应链",
                "hits": [],
            }
        },
    )

    available: bool = Field(..., description="知识库是否可用")
    total: int = Field(0, ge=0, description="命中数量")
    query: str = Field(..., description="原始query")
    hits: List[KnowledgeChunkHit] = Field(
        default_factory=list,
        description="命中文档片段列表",
    )
    message: Optional[str] = Field(
        None,
        description="补充说明，如无可用原因",
    )


class KnowledgeDocumentListResponse(BaseModel):
    """Response schema for document list."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 10,
                "documents": [],
            }
        },
    )

    total: int = Field(0, ge=0, description="文档总数")
    documents: List[KnowledgeDocumentItem] = Field(
        default_factory=list,
        description="文档列表",
    )


class KnowledgeDocumentDetailResponse(BaseModel):
    """Response schema for document detail."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "kb_20240101120000_001",
                "title": "华为产业链深度报告",
                "source_type": "markdown",
                "source_url": None,
                "file_path": "/data/kb/kb_20240101120000_001.md",
                "content_hash": "a1b2c3d4e5f6",
                "tags": ["华为", "半导体"],
                "chunks": [
                    {
                        "chunk_id": "chunk_001",
                        "chunk_index": 0,
                        "content": "华为是中国最大的芯片设计公司...",
                        "token_estimate": 150,
                    }
                ],
                "created_at": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:00:00",
            }
        },
    )

    id: str = Field(..., description="文档ID")
    title: str = Field(..., description="文档标题")
    source_type: SourceType = Field(..., description="文档来源类型")
    source_url: Optional[str] = Field(None, description="URL来源")
    file_path: Optional[str] = Field(None, description="本地文件路径")
    content_hash: str = Field(..., description="内容hash")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    chunks: List[dict[str, Any]] = Field(
        default_factory=list,
        description="文档chunks详情",
    )
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class FileUploadResponse(BaseModel):
    """Response schema for file upload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "kb_20240101120000_001",
                "title": "华为产业链深度报告.pdf",
                "source_type": "pdf",
                "chunk_count": 10,
                "content_hash": "a1b2c3d4e5f6",
                "status": "success",
                "message": "文档解析成功",
            }
        },
    )

    document_id: str = Field(..., description="文档ID")
    title: str = Field(..., description="文档标题")
    source_type: SourceType = Field(..., description="文档来源类型")
    chunk_count: int = Field(0, ge=0, description="chunk数量")
    content_hash: str = Field(..., description="内容hash")
    status: str = Field(..., description="处理状态: success, failed")
    message: str = Field(..., description="处理信息")
