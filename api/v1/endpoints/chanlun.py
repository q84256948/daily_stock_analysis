# -*- coding: utf-8 -*-
"""缠论分析 API endpoints。"""

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
SESSION_PREFIX = "chanlun"
STREAM_TIMEOUT = 300.0


class ChanlunChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


def _ensure_session_id(sid: Optional[str]) -> str:
    prefix = f"{SESSION_PREFIX}:"
    if sid and sid.startswith(prefix):
        return sid
    return f"{prefix}{sid or uuid.uuid4()}"


def _strip_prefix(sid: str) -> str:
    prefix = f"{SESSION_PREFIX}:"
    return sid[len(prefix) :] if sid.startswith(prefix) else sid


def _build_executor(config):
    from src.agent.factory import build_chanlun_executor

    return build_chanlun_executor(config)


TOOL_DISPLAY_NAMES = {
    "analyze_chanlun": "缠论分析",
}


@router.post("/chat/stream")
async def chanlun_chat_stream(request: ChanlunChatRequest):
    config = get_config()
    if not config.is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")

    session_id = _ensure_session_id(request.session_id)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def progress_callback(event: dict):
        if event.get("type") in ("tool_start", "tool_done"):
            tool = event.get("tool", "")
            event["display_name"] = TOOL_DISPLAY_NAMES.get(tool, tool)
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
                queue.put(
                    {
                        "type": "done",
                        "success": result.success,
                        "content": result.content,
                        "error": result.error,
                        "session_id": session_id,
                    }
                ),
                loop,
            )
        except Exception as exc:
            logger.error("Chanlun stream error: %s", exc)
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}),
                loop,
            )

    async def event_generator():
        fut = loop.run_in_executor(None, run_sync)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=STREAM_TIMEOUT)
                except asyncio.TimeoutError:
                    yield (
                        "data: "
                        + json.dumps({"type": "error", "message": "分析超时"})
                        + "\n\n"
                    )
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/sessions")
async def list_sessions(limit: int = 50):
    from src.storage import get_db

    sessions = get_db().get_chat_sessions(limit=limit, session_prefix=SESSION_PREFIX)
    for s in sessions:
        s["session_id"] = _strip_prefix(s["session_id"])
    return {"sessions": sessions}


@router.get("/chat/sessions/{session_id}")
async def get_session_messages(session_id: str, limit: int = 100):
    from src.storage import get_db

    full_id = _ensure_session_id(session_id)
    messages = get_db().get_conversation_messages(full_id, limit=limit)
    return {"session_id": _strip_prefix(full_id), "messages": messages}


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    from src.storage import get_db

    full_id = _ensure_session_id(session_id)
    count = get_db().delete_conversation_session(full_id)
    return {"deleted": count}
