# -*- coding: utf-8 -*-
"""Research Framework API endpoints."""

from typing import Any, List, Optional
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.research_framework import (
    PositionCreateRequest,
    PositionUpdateRequest,
    PositionItem,
    PositionListResponse,
    PositionCreatedResponse,
    PositionUpdatedResponse,
    ConcentrationItem,
    ConcentrationResponse,
    ValidatePositionRequest,
    ValidatePositionResponse,
)
from src.repositories import PositionLedgerRepo
from src.storage import DatabaseManager
from src.scoring.bayesian import validate_position_with_concentration

router = APIRouter()


def _get_db():
    """Get database session"""
    db_manager = DatabaseManager.get_instance()
    return db_manager._SessionLocal()


def _get_repo():
    """Get position ledger repo"""
    return PositionLedgerRepo(_get_db())


@router.get(
    "/positions",
    response_model=PositionListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List position ledger records",
)
def list_positions(
    stock_code: Optional[str] = Query(None, description="Filter by stock code"),
    status: Optional[str] = Query(None, description="Filter by status: open/closed"),
) -> PositionListResponse:
    """Query position ledger records"""
    repo = _get_repo()
    try:
        if stock_code:
            records = repo.get_by_stock(stock_code, status=status)
        else:
            records = repo.get_open_positions()
            if status:
                records = [r for r in records if r.status == status]

        return PositionListResponse(
            positions=[PositionItem(**r.to_dict()) for r in records],
            total=len(records),
        )
    except Exception as exc:
        raise api_error(500, "internal_error", str(exc))
    finally:
        _get_db().close()


@router.post(
    "/positions",
    response_model=PositionCreatedResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create position record",
)
def create_position(request: PositionCreateRequest) -> PositionCreatedResponse:
    """Create a new position record"""
    repo = _get_repo()
    try:
        data = request.model_dump(exclude_none=False)
        data["status"] = "open"

        record = repo.create(data)
        return PositionCreatedResponse(
            id=record.id,
            stock_code=record.stock_code,
            message="Position created successfully",
        )
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc))
    except Exception as exc:
        raise api_error(500, "internal_error", str(exc))
    finally:
        _get_db().close()


@router.patch(
    "/positions/{position_id}",
    response_model=PositionUpdatedResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Update position status",
)
def update_position(
    position_id: int,
    request: PositionUpdateRequest,
) -> PositionUpdatedResponse:
    """Update position status"""
    repo = _get_repo()
    try:
        if request.status not in ("open", "closed", "reduced", "stopped", None):
            raise ValueError(f"Invalid status: {request.status}")

        ok = repo.update_status(
            position_id,
            status=request.status,
            realized_pnl=request.realized_pnl,
        )

        if not ok:
            raise api_error(404, "not_found", f"Position not found: {position_id}")

        return PositionUpdatedResponse(
            id=position_id,
            status=request.status or "open",
            message="Position updated successfully",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc))
    except Exception as exc:
        raise api_error(500, "internal_error", str(exc))
    finally:
        _get_db().close()


@router.get(
    "/positions/concentration",
    response_model=ConcentrationResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get sector concentration",
)
def get_concentration() -> ConcentrationResponse:
    """Get sector concentration from open positions"""
    repo = _get_repo()
    try:
        positions = repo.get_open_positions()

        sector_map: dict[str, Any] = defaultdict(list)
        for pos in positions:
            market = pos.market or "unknown"
            sector_map[market].append(pos.stock_code)

        sectors = []
        total_positions = len(positions)

        for sector, codes in sector_map.items():
            if total_positions > 0:
                concentration = len(codes) / total_positions
            else:
                concentration = 0.0

            sectors.append(
                ConcentrationItem(
                    sector=sector,
                    concentration=concentration,
                    positions=codes,
                )
            )

        max_concentration = max((s.concentration for s in sectors), default=0.0)
        warning = None
        if max_concentration > 0.4:
            warning = f"Warning: High concentration ({max_concentration:.1%}) in single sector"

        return ConcentrationResponse(
            sectors=sectors,
            max_concentration=max_concentration,
            warning=warning,
        )
    except Exception as exc:
        raise api_error(500, "internal_error", str(exc))
    finally:
        _get_db().close()


@router.post(
    "/research/validate",
    response_model=ValidatePositionResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Validate position with concentration check",
)
def validate_position(request: ValidatePositionRequest) -> ValidatePositionResponse:
    """
    Validate if a position size is appropriate considering concentration.

    This endpoint checks:
    1. If the proposed position size is valid
    2. If adding this position would cause concentration issues
    """
    try:
        valid, warning = validate_position_with_concentration(
            position_suggestion=request.position_size,
            current_concentration=request.current_concentration or 0.0,
        )

        warnings = []
        if warning:
            warnings.append(warning)

        if request.current_concentration and request.current_concentration > 0.35:
            warnings.append("Current sector concentration is already high")
            return ValidatePositionResponse(
                valid=False,
                message="Position rejected due to concentration limits",
                suggested_position="reduce_existing",
                warnings=warnings,
                concentration_warning=True,
            )

        if not valid:
            return ValidatePositionResponse(
                valid=False,
                message=f"Position size {request.position_size} exceeds concentration limit",
                suggested_position="3-5%",
                warnings=warnings,
                concentration_warning=True,
            )

        return ValidatePositionResponse(
            valid=True,
            message=f"Position size {request.position_size} is acceptable",
            suggested_position=request.position_size,
            warnings=warnings if warnings else [],
            concentration_warning=bool(warning),
        )

    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc))
    except Exception as exc:
        raise api_error(500, "internal_error", str(exc))
