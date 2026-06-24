# -*- coding: utf-8 -*-
"""
Research Framework API Schemas.
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class PositionCreateRequest(BaseModel):
    """创建持仓记录请求"""

    stock_code: str = Field(..., description="股票代码")
    market: Optional[str] = Field(None, description="市场: cn/hk/us")
    action: str = Field(..., description="操作: buy/add/hold/reduce/sell")
    position_size: Optional[str] = Field(None, description="仓位建议，如 5-8%")
    prior_p: Optional[float] = Field(None, description="先验概率", ge=0, le=1)
    edge: Optional[float] = Field(None, description="Edge 值")
    posterior_p: Optional[float] = Field(None, description="后验概率", ge=0, le=1)
    value_anchor_1y: Optional[str] = Field(None, description="1年价值锚")
    value_anchor_3y: Optional[str] = Field(None, description="3年价值锚")
    value_anchor_5y: Optional[str] = Field(None, description="5年价值锚")
    rationale: Optional[str] = Field(None, description="建仓理由")
    report_id: Optional[int] = Field(None, description="关联报告ID")


class PositionUpdateRequest(BaseModel):
    """更新持仓状态请求"""

    status: Optional[str] = Field(None, description="状态: open/closed/reduced/stopped")
    realized_pnl: Optional[float] = Field(None, description="已实现盈亏")


class PositionItem(BaseModel):
    """持仓记录项"""

    id: int
    report_id: Optional[int] = None
    stock_code: str
    market: Optional[str] = None
    action: str
    position_size: Optional[str] = None
    prior_p: Optional[float] = None
    edge: Optional[float] = None
    posterior_p: Optional[float] = None
    value_anchor_1y: Optional[str] = None
    value_anchor_3y: Optional[str] = None
    value_anchor_5y: Optional[str] = None
    status: str
    rationale: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    realized_pnl: Optional[float] = None
    evaluated_at: Optional[datetime] = None


class PositionListResponse(BaseModel):
    """持仓列表响应"""

    positions: List[PositionItem]
    total: int


class PositionCreatedResponse(BaseModel):
    """持仓创建响应"""

    id: int
    stock_code: str
    message: str = "Position created successfully"


class PositionUpdatedResponse(BaseModel):
    """持仓更新响应"""

    id: int
    status: str
    message: str = "Position updated successfully"


class ConcentrationItem(BaseModel):
    """集中度项"""

    sector: str
    concentration: float = Field(..., ge=0, le=1)
    positions: List[str]


class ConcentrationResponse(BaseModel):
    """集中度响应"""

    sectors: List[ConcentrationItem]
    max_concentration: float = Field(..., ge=0, le=1)
    warning: Optional[str] = None


class ValidatePositionRequest(BaseModel):
    """验证仓位请求"""

    stock_code: str = Field(..., description="股票代码")
    position_size: str = Field(..., description="拟持仓仓位的百分比范围，如 5-8%")
    current_concentration: Optional[float] = Field(
        None, description="当前赛道集中度 0-1", ge=0, le=1
    )


class ValidatePositionResponse(BaseModel):
    """验证仓位响应"""

    valid: bool
    message: str
    suggested_position: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    concentration_warning: bool = False
