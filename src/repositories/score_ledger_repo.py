# -*- coding: utf-8 -*-
"""
Score Ledger Repository.

CRUD operations for six-dimension scoring snapshots.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Session

from src.storage import Base


class ScoreLedger(Base):
    """Six-dimension score ledger"""

    __tablename__ = "score_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(
        Integer,
        ForeignKey("analysis_history.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    stock_code = Column(String(10), nullable=False, index=True)
    market = Column(String(8), nullable=True)

    dimension_total = Column(Float, nullable=False)

    supply_chain_score = Column(Float, nullable=True)
    fundamental_score = Column(Float, nullable=True)
    capital_score = Column(Float, nullable=True)
    technical_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    macro_score = Column(Float, nullable=True)

    prior_p = Column(Float, nullable=True)
    market_implied_p = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)
    posterior_p = Column(Float, nullable=True)
    position_suggestion = Column(String(10), nullable=True)

    scoring_version = Column(String(16), nullable=False, default="v1")
    raw_scores_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)

    __table_args__ = (
        Index("ix_score_ledger_stock_created", "stock_code", "created_at"),
        Index("ix_score_ledger_report", "report_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "stock_code": self.stock_code,
            "market": self.market,
            "dimension_total": self.dimension_total,
            "supply_chain_score": self.supply_chain_score,
            "fundamental_score": self.fundamental_score,
            "capital_score": self.capital_score,
            "technical_score": self.technical_score,
            "sentiment_score": self.sentiment_score,
            "macro_score": self.macro_score,
            "prior_p": self.prior_p,
            "market_implied_p": self.market_implied_p,
            "edge": self.edge,
            "posterior_p": self.posterior_p,
            "position_suggestion": self.position_suggestion,
            "scoring_version": self.scoring_version,
            "raw_scores_json": self.raw_scores_json,
            "created_at": self.created_at.isoformat()
            if self.created_at is not None
            else None,
        }


class ScoreLedgerRepo:
    """Score ledger data access"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: Dict[str, Any]) -> ScoreLedger:
        """Create score record"""
        record = ScoreLedger(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id: int) -> Optional[ScoreLedger]:
        """Get by ID"""
        return self.db.query(ScoreLedger).filter(ScoreLedger.id == id).first()

    def get_by_stock(self, stock_code: str, limit: int = 10) -> List[ScoreLedger]:
        """Get by stock code with limit"""
        return (
            self.db.query(ScoreLedger)
            .filter(ScoreLedger.stock_code == stock_code)
            .order_by(ScoreLedger.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_latest_by_stock(self, stock_code: str) -> Optional[ScoreLedger]:
        """Get latest score for stock"""
        return (
            self.db.query(ScoreLedger)
            .filter(ScoreLedger.stock_code == stock_code)
            .order_by(ScoreLedger.created_at.desc())
            .first()
        )

    def get_recent(self, limit: int = 50) -> List[ScoreLedger]:
        """Get recent scores"""
        return (
            self.db.query(ScoreLedger)
            .order_by(ScoreLedger.created_at.desc())
            .limit(limit)
            .all()
        )
