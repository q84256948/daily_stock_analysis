# -*- coding: utf-8 -*-
"""
Belief Ledger Repository.

CRUD operations for probability and evidence ledger.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Session

from src.storage import Base


class BeliefLedger(Base):
    """Probability and evidence ledger"""

    __tablename__ = "belief_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(
        Integer,
        ForeignKey("analysis_history.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    stock_code = Column(String(10), nullable=False, index=True)
    market = Column(String(8), nullable=True)

    prior_p = Column(Float, nullable=False)
    market_implied_p = Column(Float, nullable=False)
    edge = Column(Float, nullable=False)
    posterior_p = Column(Float, nullable=False)

    evidence_seq = Column(Text, nullable=True)
    scoring_version = Column(String(16), nullable=False, default="v1")
    weight_snapshot = Column(Text, nullable=True)

    dimension_total = Column(Float, nullable=True)
    supply_chain_score = Column(Float, nullable=True)
    fundamental_score = Column(Float, nullable=True)
    capital_score = Column(Float, nullable=True)
    technical_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    macro_score = Column(Float, nullable=True)

    future_returns = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)

    __table_args__ = (
        Index("ix_belief_ledger_stock_created", "stock_code", "created_at"),
        Index("ix_belief_ledger_report", "report_id"),
        Index("ix_belief_ledger_edge", "edge"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "stock_code": self.stock_code,
            "market": self.market,
            "prior_p": self.prior_p,
            "market_implied_p": self.market_implied_p,
            "edge": self.edge,
            "posterior_p": self.posterior_p,
            "evidence_seq": self.evidence_seq,
            "scoring_version": self.scoring_version,
            "weight_snapshot": self.weight_snapshot,
            "dimension_total": self.dimension_total,
            "supply_chain_score": self.supply_chain_score,
            "fundamental_score": self.fundamental_score,
            "capital_score": self.capital_score,
            "technical_score": self.technical_score,
            "sentiment_score": self.sentiment_score,
            "macro_score": self.macro_score,
            "future_returns": self.future_returns,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BeliefLedgerRepo:
    """Belief ledger data access"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: Dict[str, Any]) -> BeliefLedger:
        """Create belief record"""
        record = BeliefLedger(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id: int) -> Optional[BeliefLedger]:
        """Get by ID"""
        return self.db.query(BeliefLedger).filter(BeliefLedger.id == id).first()

    def get_by_stock(self, stock_code: str, limit: int = 20) -> List[BeliefLedger]:
        """Get by stock code with limit"""
        return (
            self.db.query(BeliefLedger)
            .filter(BeliefLedger.stock_code == stock_code)
            .order_by(BeliefLedger.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_latest_by_stock(self, stock_code: str) -> Optional[BeliefLedger]:
        """Get latest belief for stock"""
        return (
            self.db.query(BeliefLedger)
            .filter(BeliefLedger.stock_code == stock_code)
            .order_by(BeliefLedger.created_at.desc())
            .first()
        )

    def get_high_edge(self, min_edge: float = 0.1, limit: int = 20) -> List[BeliefLedger]:
        """Get records with high edge"""
        return (
            self.db.query(BeliefLedger)
            .filter(BeliefLedger.edge >= min_edge)
            .order_by(BeliefLedger.edge.desc())
            .limit(limit)
            .all()
        )

    def update_future_returns(self, id: int, future_returns: str) -> bool:
        """Update future returns for backtest"""
        record = self.get_by_id(id)
        if not record:
            return False
        record.future_returns = future_returns
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
