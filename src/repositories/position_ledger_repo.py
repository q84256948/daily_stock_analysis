# -*- coding: utf-8 -*-
"""
Position Ledger Repository.

CRUD operations for long-term position tracking.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import Session

from src.storage import Base


class PositionLedger(Base):
    """Long-term position ledger"""

    __tablename__ = "position_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(
        Integer,
        ForeignKey("analysis_history.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    stock_code = Column(String(10), nullable=False, index=True)
    market = Column(String(8), nullable=True)
    action = Column(String(20), nullable=False)
    position_size = Column(String(10), nullable=True)
    prior_p = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)
    posterior_p = Column(Float, nullable=True)
    value_anchor_1y = Column(String(50), nullable=True)
    value_anchor_3y = Column(String(50), nullable=True)
    value_anchor_5y = Column(String(50), nullable=True)
    status = Column(String(16), nullable=False, default="open")
    rationale = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    realized_pnl = Column(Float, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_position_ledger_stock_created", "stock_code", "created_at"),
        Index("ix_position_ledger_status", "status"),
        Index("ix_position_ledger_report", "report_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "stock_code": self.stock_code,
            "market": self.market,
            "action": self.action,
            "position_size": self.position_size,
            "prior_p": self.prior_p,
            "edge": self.edge,
            "posterior_p": self.posterior_p,
            "value_anchor_1y": self.value_anchor_1y,
            "value_anchor_3y": self.value_anchor_3y,
            "value_anchor_5y": self.value_anchor_5y,
            "status": self.status,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat()
            if bool(self.created_at)
            else None,
            "updated_at": self.updated_at.isoformat()
            if bool(self.updated_at)
            else None,
            "realized_pnl": self.realized_pnl,
            "evaluated_at": self.evaluated_at.isoformat()
            if bool(self.evaluated_at)
            else None,
        }


class PositionLedgerRepo:
    """Position ledger data access"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: Dict[str, Any]) -> PositionLedger:
        """Create position record"""
        record = PositionLedger(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id: int) -> Optional[PositionLedger]:
        """Get by ID"""
        return self.db.query(PositionLedger).filter(PositionLedger.id == id).first()

    def get_by_stock(
        self, stock_code: str, status: Optional[str] = None
    ) -> List[PositionLedger]:
        """Get by stock code"""
        query = self.db.query(PositionLedger).filter(
            PositionLedger.stock_code == stock_code
        )
        if status:
            query = query.filter(PositionLedger.status == status)
        return query.order_by(PositionLedger.created_at.desc()).all()

    def get_open_positions(self) -> List[PositionLedger]:
        """Get all open positions"""
        return (
            self.db.query(PositionLedger)
            .filter(PositionLedger.status == "open")
            .order_by(PositionLedger.created_at.desc())
            .all()
        )

    def update_status(
        self, id: int, status: str, realized_pnl: Optional[float] = None
    ) -> bool:
        """Update position status"""
        record = self.get_by_id(id)
        if not record:
            return False

        record.status = status  # type: ignore[reportAttributeAccessIssue]
        if realized_pnl is not None:
            record.realized_pnl = realized_pnl  # type: ignore[reportAttributeAccessIssue]
        record.evaluated_at = datetime.now()  # type: ignore[reportAttributeAccessIssue]

        self.db.commit()
        return True

    def delete(self, id: int) -> bool:
        """Delete record"""
        record = self.get_by_id(id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
