# -*- coding: utf-8 -*-
"""郑希投研分析 API endpoints.

对话 + 会话管理，与问股 ``/agent`` 端点结构一致但完全隔离：

- Executor 走 :func:`src.agent.factory.build_zhengxi_executor`
  （独立工具集 + 郑希专属 system prompt，不碰问股全局工具）。
- 会话 ``session_id`` 统一用 ``zhengxi:`` 前缀，列表查询固定按 ``zhengxi``
  前缀过滤，复用 :func:`src.storage.get_chat_sessions` 的 ``session_prefix``
  机制——**后端存储零 schema 改动**，与问股会话天然隔离。
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter()

# 郑希工具中文显示名（SSE 进度事件用）
ZHENGXI_TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "search_zhengxi_views": "检索郑希观点",
    "get_zhengxi_fund_data": "查询基金数据",
    "score_fund_zhengxi": "郑希框架评分",
}

# 会话命名空间前缀，与问股会话隔离（复用 storage 的 session_prefix 过滤）
SESSION_PREFIX = "zhengxi"


# ============================================================
# Schemas
# ============================================================

class ZhengxiChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ZhengxiChatResponse(BaseModel):
    success: bool
    content: str
    session_id: str
    error: Optional[str] = None


class ZhengxiSessionItem(BaseModel):
    session_id: str
    title: str
    message_count: int
    created_at: Optional[str] = None
    last_active: Optional[str] = None


class ZhengxiSessionsResponse(BaseModel):
    sessions: List[ZhengxiSessionItem]


class ZhengxiSessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]


# ============================================================
# Helpers
# ============================================================

def _ensure_zhengxi_session_id(session_id: Optional[str]) -> str:
    """保证 session_id 带 ``zhengxi:`` 前缀，缺失则生成。"""
    prefix = f"{SESSION_PREFIX}:"
    if session_id and session_id.startswith(prefix):
        return session_id
    if session_id:  # 前端传了裸 id，补前缀
        return f"{prefix}{session_id}"
    return f"{prefix}{uuid.uuid4()}"


def _strip_zhengxi_prefix(session_id: str) -> str:
    """去掉 ``zhengxi:`` 前缀。

    list/get 端点返回 session_id 前调用，使前端拿到的 id 与 localStorage 存储
    的无前缀格式一致——避免刷新后 ``loadInitialSession`` 因前缀不匹配而无法恢复会话。
    """
    prefix = f"{SESSION_PREFIX}:"
    return session_id[len(prefix):] if session_id.startswith(prefix) else session_id


def _build_executor(config):
    from src.agent.factory import build_zhengxi_executor
    return build_zhengxi_executor(config)


def _require_agent(config) -> None:
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")


# ============================================================
# Chat (non-streaming)
# ============================================================

@router.post("/chat", response_model=ZhengxiChatResponse)
async def zhengxi_chat(request: ZhengxiChatRequest):
    """郑希投研问答（非流式）。"""
    config = get_config()
    _require_agent(config)
    session_id = _ensure_zhengxi_session_id(request.session_id)
    try:
        executor = _build_executor(config)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: executor.chat(
                message=request.message,
                session_id=session_id,
                context=request.context,
            ),
        )
        return ZhengxiChatResponse(
            success=result.success,
            content=result.content,
            session_id=session_id,
            error=result.error,
        )
    except Exception as exc:
        logger.error("Zhengxi chat API failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================
# Chat (SSE streaming)
# ============================================================

@router.post("/chat/stream")
async def zhengxi_chat_stream(request: ZhengxiChatRequest):
    """郑希投研问答 SSE 流式端点。

    SSE 事件 ``type`` 与问股一致：``thinking`` / ``tool_start`` / ``tool_done``
    / ``generating`` / ``done`` / ``error``。
    """
    config = get_config()
    _require_agent(config)
    session_id = _ensure_zhengxi_session_id(request.session_id)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def progress_callback(event: dict[str, Any]):
        if event.get("type") in ("tool_start", "tool_done"):
            tool = event.get("tool", "")
            event["display_name"] = ZHENGXI_TOOL_DISPLAY_NAMES.get(tool, tool)
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def run_sync():
        try:
            executor = _build_executor(config)
            result = executor.chat(
                message=request.message,
                session_id=session_id,
                progress_callback=progress_callback,
                context=request.context,
            )
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "done",
                    "success": result.success,
                    "content": result.content,
                    "error": result.error,
                    "total_steps": result.total_steps,
                    "session_id": session_id,
                }),
                loop,
            )
        except Exception as exc:
            logger.error("Zhengxi stream error: %s", exc, exc_info=True)
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}),
                loop,
            )

    async def event_generator():
        fut = loop.run_in_executor(None, run_sync)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield "data: " + json.dumps(
                        {"type": "error", "message": "分析超时"}, ensure_ascii=False
                    ) + "\n\n"
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as exc:
                logger.debug("zhengxi executor cleanup error (ignored): %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# Session CRUD（会话隔离：固定 zhengxi 前缀）
# ============================================================

@router.get("/chat/sessions", response_model=ZhengxiSessionsResponse)
async def list_zhengxi_sessions(limit: int = 50):
    """郑希会话列表（固定按 ``zhengxi`` 前缀过滤，与问股隔离）。

    返回的 session_id 去除 ``zhengxi:`` 前缀，与前端 localStorage 的无前缀
    格式保持一致，确保刷新后 ``loadInitialSession`` 能正确恢复当前会话。
    """
    from src.storage import get_db
    sessions = get_db().get_chat_sessions(
        limit=limit,
        session_prefix=SESSION_PREFIX,
    )
    for s in sessions:
        s["session_id"] = _strip_zhengxi_prefix(s["session_id"])
    return ZhengxiSessionsResponse(sessions=sessions)


@router.get("/chat/sessions/{session_id}", response_model=ZhengxiSessionMessagesResponse)
async def get_zhengxi_session_messages(session_id: str, limit: int = 100):
    """获取单个郑希会话的完整消息。

    容忍前端传入无前缀 session_id（与 list 返回格式一致），内部统一补前缀后查 DB。
    """
    from src.storage import get_db
    full_id = _ensure_zhengxi_session_id(session_id)
    messages = get_db().get_conversation_messages(full_id, limit=limit)
    return ZhengxiSessionMessagesResponse(
        session_id=_strip_zhengxi_prefix(full_id), messages=messages
    )


@router.delete("/chat/sessions/{session_id}")
async def delete_zhengxi_session(session_id: str):
    """删除指定郑希会话。

    容忍前端传入无前缀 session_id，内部统一补前缀后删除。
    """
    from src.storage import get_db
    full_id = _ensure_zhengxi_session_id(session_id)
    count = get_db().delete_conversation_session(full_id)
    return {"deleted": count}
