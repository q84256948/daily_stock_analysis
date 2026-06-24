# -*- coding: utf-8 -*-
"""A股深度投研报告 API endpoints（五层穿透框架）。

形态：表单输入股票 → SSE 流式生成 → 报告展示 + PDF 下载 + 历史列表。
与问股/郑希/供应链的对话框模式不同（无多轮会话），但复用同一套 SSE 线程池包装。

接口（5 个，挂 ``/api/v1/deep-research``，继承全局 AuthMiddleware）：
- ``POST /generate/stream``  SSE 流式生成（thinking/tool_start/tool_done/generating/done/error/heartbeat）
- ``GET  /reports``          历史报告列表（分页）
- ``GET  /reports/{id}``     报告详情（含 Markdown 正文）
- ``DELETE /reports/{id}``   删除报告（元数据 + .md + .pdf）
- ``GET  /reports/{id}/pdf`` PDF 下载（惰性生成，``asyncio.to_thread`` + Semaphore 限流）

安全：
- ``report_id`` 白名单 ``^\\d{6}_\\d{12}$`` + ``_resolve_asset_path`` 双重防穿越。
- 入口 A 股校验（``normalize_a_share``），非 A 股直接 HTTP 400。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.config import get_config
from src.services.deep_research_service import (
    DeepResearchInputError,
    deep_research_service,
    get_deep_research_dir,
    normalize_a_share,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# SSE event 间隔 timeout（五层穿透 + 报告生成 2–5 分钟，对齐 executor 1200s）
STREAM_QUEUE_TIMEOUT_S = 1200.0
# 心跳间隔（保活连接，防 nginx/uvicorn 静默切断）
HEARTBEAT_INTERVAL_S = 30.0

# report_id 白名单：{6位A股代码}_{YYYYMMDDHHmm}，可选 _序号 后缀（同分钟冲突追加，如 _1）
# 后缀仅允许 _\d+，路径穿越字符（../ 等）仍被拒绝
_REPORT_ID_RE = re.compile(r"^\d{6}_\d{12}(_\d+)?$")


# ============================================================
# Schemas
# ============================================================

class DeepResearchRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    report_type: str = "deep"


class ReportListItem(BaseModel):
    id: str
    stock_code: str
    stock_name: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = None
    quality_score: Optional[int] = None
    missing_layers: List[str] = []
    has_pdf: bool = False


class ReportListResponse(BaseModel):
    success: bool
    data: List[ReportListItem]
    total: int


class ReportDetailResponse(BaseModel):
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
    """将报告文件路径收敛到 deep_research 目录内（防穿越第二道关）。

    复用 app._resolve_asset_path 的思路：resolve 后必须 is_relative_to。
    """
    if not path_str:
        return None
    try:
        root = get_deep_research_dir().resolve()
        candidate = Path(path_str).resolve()
        if candidate.is_relative_to(root):
            return candidate
    except (OSError, ValueError):
        pass
    return None


def _require_agent(config) -> None:
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")


# ============================================================
# 生成（SSE 流式）
# ============================================================

@router.post("/generate/stream")
async def generate_stream(request: DeepResearchRequest):
    """SSE 流式生成深度投研报告。

    入口先同步校验 A 股代码（非 A 股直接 400，不浪费 SSE 连接），
    通过后在线程池跑 ``deep_research_service.generate_report``，
    progress_callback 把事件塞入 asyncio.Queue，event_generator 消费并加 30s 心跳。
    """
    config = get_config()
    _require_agent(config)

    # 入口预校验（非 A 股直接 400）
    try:
        normalize_a_share(request.stock_code)
    except DeepResearchInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    loop = asyncio.get_running_loop()
    queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

    def progress_callback(event: Dict[str, Any]) -> None:
        # executor/service 在工作线程调用，需跨线程把事件塞回 event loop
        try:
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        except RuntimeError:
            pass  # loop 已关闭，忽略

    def run_sync() -> None:
        try:
            deep_research_service.generate_report(
                raw_code=request.stock_code,
                raw_name=request.stock_name,
                report_type=request.report_type,
                progress_callback=progress_callback,
            )
            # done 事件由 service.generate_report 内部推
        except DeepResearchInputError as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}), loop
            )
        except Exception as exc:
            logger.error("[DeepResearch] stream error: %s", exc, exc_info=True)
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
                    # 心跳：保活连接（防 nginx 静默切断）
                    if time.time() - last_event_time >= HEARTBEAT_INTERVAL_S:
                        yield "data: " + json.dumps({"type": "heartbeat"}, ensure_ascii=False) + "\n\n"
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
                logger.debug("[DeepResearch] executor cleanup error (ignored): %s", exc)

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
    stock_code: Optional[str] = Query(None),
):
    """历史报告列表（分页，按时间倒序）。"""
    rows, total = deep_research_service.list_reports(
        limit=limit, offset=offset, stock_code=stock_code
    )
    items = [
        ReportListItem(
            id=r.get("id", ""),
            stock_code=r.get("stock_code", ""),
            stock_name=r.get("stock_name"),
            created_at=r.get("created_at"),
            status=r.get("status"),
            quality_score=r.get("quality_score"),
            missing_layers=r.get("missing_layers", []),
            has_pdf=bool(r.get("pdf_path")),
        )
        for r in rows
    ]
    return ReportListResponse(success=True, data=items, total=total)


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(report_id: str):
    """报告详情（含 Markdown 正文）。"""
    _validate_report_id(report_id)
    data = deep_research_service.get_report(report_id)
    if data is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ReportDetailResponse(success=True, data=data)


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    """删除报告（元数据 + .md + .pdf 文件）。"""
    _validate_report_id(report_id)
    ok = deep_research_service.delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail="报告不存在")
    logger.info("[DeepResearch] 删除报告 %s（via API）", report_id)
    return {"success": True, "deleted": report_id}


# ============================================================
# PDF 下载（惰性生成）
# ============================================================

@router.get("/reports/{report_id}/pdf")
async def download_pdf(report_id: str):
    """PDF 下载：惰性生成（首次请求在线程池生成，后续直接发文件）。

    PDF 生成用 ``asyncio.to_thread`` 包 ``md2pdf.markdown_to_pdf_file``，
    避免同步渲染阻塞 event loop；模块级 Semaphore(1) 限并发防爆内存。
    """
    _validate_report_id(report_id)

    # 区分「报告不存在」与「渲染失败」，给出更准确的错误信息
    record = await asyncio.to_thread(deep_research_service.get_report, report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    # 惰性生成（线程池，防阻塞）
    pdf_path_str = await asyncio.to_thread(deep_research_service.get_pdf_path, report_id)
    if not pdf_path_str:
        raise HTTPException(
            status_code=404,
            detail="PDF 生成失败（渲染依赖不可用或报告正文为空），请稍后重试",
        )

    # 防穿越第二道关：路径必须收敛在 deep_research 目录内
    safe_path = _resolve_safe_path(pdf_path_str)
    if safe_path is None or not safe_path.exists():
        raise HTTPException(status_code=404, detail="PDF 文件不存在")

    return FileResponse(
        str(safe_path),
        media_type="application/pdf",
        filename=f"deep_research_{report_id}.pdf",  # 触发 Content-Disposition: attachment
    )
