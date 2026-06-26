# -*- coding: utf-8 -*-
"""
三层防御体系示例：风控 Skill 的输入输出与核心计算。

- Layer 3 (Pydantic v2): RiskCheckRequest / RiskCheckResult 守卫 I/O 边界
- Layer 2 (icontract): check_risk 的业务前置/后置条件
- Layer 1 (mypy/pyright): 完整类型注解

该模块作为 OpenClaw Skill 与量化金融基础设施的类型-契约-数据防御范式试点。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from icontract import ensure, require
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class RiskCheckRequest(BaseModel):
    """风控检查请求：Pydantic 负责数据形状与简单数值约束。"""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        validate_assignment=True,
    )

    user_id: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[a-f0-9]{32}$",
            description="用户 ID，32 位 hex",
        ),
    ]
    symbol: Annotated[
        str,
        Field(..., min_length=1, max_length=20, description="交易对，如 BTC-USDT"),
    ]
    side: Literal["BUY", "SELL"] = Field(..., description="订单方向")
    price: Annotated[
        Decimal,
        Field(
            ...,
            gt=Decimal("0"),
            decimal_places=8,
            description="价格，必须为正，最多 8 位小数",
        ),
    ]
    quantity: Annotated[
        Decimal,
        Field(..., gt=Decimal("0"), description="数量，必须为正"),
    ]
    leverage: Annotated[
        Decimal,
        Field(default=Decimal("1"), gt=Decimal("0"), le=Decimal("100")),
    ]
    account_balance: Annotated[
        Decimal,
        Field(..., gt=Decimal("0"), description="账户余额，必须为正"),
    ]

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """交易对必须包含 '-' 分隔符。"""
        if "-" not in v:
            raise ValueError("交易对格式必须为 BASE-QUOTE")
        return v.upper()

    @property
    def notional(self) -> Decimal:
        """名义价值 = 价格 × 数量。"""
        return self.price * self.quantity


class RiskCheckResult(BaseModel):
    """风控检查结果：Pydantic 负责输出结构一致性。"""

    model_config = ConfigDict(
        strict=True,
        frozen=False,
        validate_assignment=True,
    )

    passed: bool = Field(..., description="是否通过风控")
    margin_required: Annotated[
        Decimal,
        Field(..., gt=Decimal("0"), description="所需保证金"),
    ]
    margin_ratio: Annotated[
        Decimal,
        Field(..., gt=Decimal("0"), description="保证金率"),
    ]
    reject_reason: str | None = Field(
        default=None,
        description="拒绝原因，通过时为 None",
    )
    checked_at: datetime = Field(
        default_factory=_utc_now,
        description="风控检查时间",
    )


@require(lambda req: req.leverage >= Decimal("1"), "杠杆必须 >= 1")
@require(lambda req: req.account_balance > Decimal("0"), "账户余额必须为正")
@ensure(
    lambda req, result: result.margin_required == req.notional / req.leverage,
    "保证金计算公式必须精确匹配",
)
@ensure(
    lambda req, result: result.margin_ratio == result.margin_required / req.account_balance,
    "保证金占用率计算必须正确",
)
@ensure(
    lambda result: Decimal("0") <= result.margin_ratio if result.passed else True,
    "通过风控时，保证金占用率必须非负",
)
def check_risk(req: RiskCheckRequest) -> RiskCheckResult:
    """
    风控检查：计算保证金占用率，判断是否可以开仓。

    三层验证：
    - Pydantic：请求体形状、symbol 格式、数值范围
    - mypy/pyright：参数/返回类型、Decimal 使用
    - icontract：保证金公式与业务不变量
    """
    margin_required = req.notional / req.leverage
    margin_ratio = margin_required / req.account_balance

    if margin_ratio > Decimal("0.1"):
        return RiskCheckResult(
            passed=False,
            margin_required=margin_required,
            margin_ratio=margin_ratio,
            reject_reason="保证金占用率超过账户余额 10%",
        )

    return RiskCheckResult(
        passed=True,
        margin_required=margin_required,
        margin_ratio=margin_ratio,
    )
