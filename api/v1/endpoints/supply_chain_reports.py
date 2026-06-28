# -*- coding: utf-8 -*-
"""供应链分析表单式报告 API endpoints。

形态：表单输入分析主题（+可选供应链线索）→ SSE 流式生成 → 报告展示 + PDF 下载 + 历史列表。
与旧 ``supply_chain.py`` 的对话框模式隔离（无多轮会话、走独立报告表），但复用同一套
SSE 线程池包装与供应链工具中文显示名。旧 chat 端点保留不变，本模块只新增报告式端点。

接口（5 个，挂 ``/api/v1/supply-chain/...``，与旧 chat 同前缀、路径不冲突）：
- ``POST /generate/stream``  SSE 流式生成（thinking/tool_start/tool_done/generating/done/error/heartbeat）
- ``GET  /reports``          历史报告列表（分页）
- ``GET  /reports/{id}``     报告详情（含 Markdown 正文）
- ``DELETE /reports/{id}``   删除报告（元数据 + .md + .pdf）
- ``GET  /reports/{id}/pdf`` PDF 下载（惰性生成，``asyncio.to_thread``）

安全：
- ``report_id`` 白名单 ``^sc_\\d{12}(_\\d+)?$`` + ``_resolve_safe_path`` 双重防路径穿越。
- ``topic`` 长度/非空由 Pydantic v2 strict 在解析期校验（畸形直接 HTTP 422）；
  语义级空主题（trim 后为空）由 service.generate_report 兜底（run_sync 捕获后发 error 事件）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.config import get_config
from src.services.supply_chain_report_service import (
    SupplyChainReportInputError,
    get_supply_chain_report_dir,
    supply_chain_report_service,
)
# 复用旧 supply_chain 端点的工具中文显示名（供应链共享问股工具集 + 专属打分工具）
from api.v1.endpoints.supply_chain import SUPPLY_CHAIN_TOOL_DISPLAY_NAMES

logger = logging.getLogger(__name__)

router = APIRouter()

# SSE event 间隔 timeout（9 步深度调研长任务，与旧 supply_chain chat 一致 1200s）
STREAM_QUEUE_TIMEOUT_S = 1200.0
HEARTBEAT_INTERVAL_S = 30.0

# report_id 白名单：sc_{YYYYMMDDHHmm}，可选 _序号 后缀
_REPORT_ID_RE = re.compile(r"^sc_\d{12}(_\d+)?$")


# ============================================================
# Schemas
# ============================================================

class SupplyChainGenerateRequest(BaseModel):
    # Layer 3（数据守门员）：I/O 边界第一道关 —— 格式/范围在解析期校验，
    # 畸形输入直接 422，不浪费 SSE 线程。语义级空主题校验在 service 层兜底。
    model_config = ConfigDict(strict=True, frozen=True, validate_assignment=True)

    topic: Annotated[str, Field(..., min_length=1, max_length=1000, description="分析主题")]
    research_hint: Optional[Annotated[str, Field(max_length=2000)]] = None


class ReportListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    topic: str
    research_hint: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = None
    has_pdf: bool = False


class ReportListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    data: List[ReportListItem]
    total: int


class ReportDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    data: Dict[str, Any]


# ============================================================
# Helpers
# ============================================================

def _validate_report_id(report_id: str) -> str:
    """report_id 白名单校验（防路径穿越第一道关）。不通过抛 404。"""
    if not report_id or not _REPORT_ID_RE.fullmatch(report_id):
        raise HTTPException(status_code=404, detail="报告不存在")
    return report_id


def _resolve_safe_path(path_str: str) -> Optional[Path]:
    """将报告文件路径收敛到 supply_chain 目录内（防穿越第二道关）。"""
    if not path_str:
        return None
    try:
        root = get_supply_chain_report_dir().resolve()
        candidate = Path(path_str).resolve()
        if candidate.is_relative_to(root):
            return candidate
    except (OSError, ValueError):
        pass
    return None


def _require_agent(config: Any) -> None:
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")


# ============================================================
# 生成（SSE 流式）
# ============================================================

@router.post("/generate/stream")
async def generate_stream(request: SupplyChainGenerateRequest) -> StreamingResponse:
    """SSE 流式生成供应链报告。

    入口由 Pydantic 校验 topic 长度/非空（畸形 422，不浪费 SSE 连接）；
    语义级空主题校验在 service.generate_report 内，run_sync 捕获后发 error 事件。
    通过后在线程池跑 ``supply_chain_report_service.generate_report``，
    progress_callback 把事件塞入 asyncio.Queue，event_generator 消费并加 30s 心跳。
    """
    config = get_config()
    _require_agent(config)

    loop = asyncio.get_running_loop()
    queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

    def progress_callback(event: Dict[str, Any]) -> None:
        # 给工具事件注入中文显示名（与旧 supply_chain chat 一致）
        if event.get("type") in ("tool_start", "tool_done"):
            tool = event.get("tool", "")
            event["display_name"] = SUPPLY_CHAIN_TOOL_DISPLAY_NAMES.get(tool, tool)
        try:
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        except RuntimeError:
            pass  # loop 已关闭，忽略

    def run_sync() -> None:
        try:
            supply_chain_report_service.generate_report(
                raw_topic=request.topic,
                raw_hint=request.research_hint,
                progress_callback=progress_callback,
            )
        except SupplyChainReportInputError as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}), loop
            )
        except Exception as exc:
            logger.error("[SupplyChainReport] stream error: %s", exc, exc_info=True)
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": f"生成失败：{exc}"}), loop
            )

    async def event_generator():
        import time

        fut = loop.run_in_executor(None, run_sync)
        last_event_time = time.time()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    if time.time() - last_event_time >= HEARTBEAT_INTERVAL_S:
                        yield "data: " + json.dumps(
                            {"type": "heartbeat"}, ensure_ascii=False
                        ) + "\n\n"
                    continue
                last_event_time = time.time()
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as exc:
                logger.debug("[SupplyChainReport] executor cleanup error (ignored): %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 关缓冲，配合 proxy_read_timeout >= 1200s
            "Connection": "keep-alive",
        },
    )


# ============================================================
# 历史报告 CRUD
# ============================================================

@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """历史报告列表（分页，按时间倒序）。"""
    rows, total = supply_chain_report_service.list_reports(limit=limit, offset=offset)
    items = [
        ReportListItem(
            id=r.get("id", ""),
            topic=r.get("topic", ""),
            research_hint=r.get("research_hint"),
            created_at=r.get("created_at"),
            status=r.get("status"),
            has_pdf=bool(r.get("pdf_path")),
        )
        for r in rows
    ]
    return ReportListResponse(success=True, data=items, total=total)


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(report_id: str):
    """报告详情（含 Markdown 正文）。"""
    _validate_report_id(report_id)
    data = supply_chain_report_service.get_report(report_id)
    if data is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ReportDetailResponse(success=True, data=data)


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    """删除报告（元数据 + .md + .pdf 文件）。"""
    _validate_report_id(report_id)
    ok = supply_chain_report_service.delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="报告不存在")
    logger.info("[SupplyChainReport] 删除报告 %s（via API）", report_id)
    return {"success": True, "deleted": report_id}


# ============================================================
# PDF 下载（惰性生成）
# ============================================================

@router.get("/reports/{report_id}/pdf")
async def download_pdf(report_id: str):
    """PDF 下载：惰性生成（首次请求在线程池生成，后续直接发文件）。"""
    _validate_report_id(report_id)

    record = await asyncio.to_thread(supply_chain_report_service.get_report, report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    pdf_path_str = await asyncio.to_thread(
        supply_chain_report_service.get_pdf_path, report_id
    )
    if not pdf_path_str:
        raise HTTPException(
            status_code=404,
            detail="PDF 生成失败（渲染依赖不可用或报告正文为空），请稍后重试",
        )

    safe_path = _resolve_safe_path(pdf_path_str)
    if safe_path is None or not safe_path.exists():
        raise HTTPException(status_code=404, detail="PDF 文件不存在")

    return FileResponse(
        str(safe_path),
        media_type="application/pdf",
        filename=f"supply_chain_{report_id}.pdf",
    )
