# -*- coding: utf-8 -*-
"""供应链分析表单式报告编排服务。

职责（编排层，不含 LLM/数据获取细节）：
1. 校验和规范化 ``topic`` / ``research_hint``（分析主题必填，线索可选、一次性）。
2. 生成唯一 ``report_id``（``sc_{YYYYMMDDHHmm}_{seq}``，纯 ASCII，安全）。
3. 组装本轮 prompt（线索非空时注入线索调查指令）。
4. 调用 :class:`SupplyChainExecutor.chat`（内部 session ``supply_chain_report:{report_id}``，
   与旧聊天会话 ``supply_chain:`` 隔离），从 ``AgentResult`` 派生 status。
5. 报告存盘：Markdown 写文件（``reports/supply_chain/``）+ 元数据写 SQLite。
6. 列表/详情/删除代理 + PDF 惰性生成入口（复用共享 ``src/md2pdf.py``）+ 超额清理。

不直接跑 ReAct 循环（在 executor）；不直接做 PDF 渲染（在 md2pdf）。
不新增配置项：报告保留数量用模块常量 ``_MAX_REPORTS``。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from src.config import get_config
from src.storage import get_db

if TYPE_CHECKING:
    # 仅类型检查期导入（from __future__ annotations 使运行期注解为字符串，无循环 import）
    from src.agent.supply_chain_executor import SupplyChainExecutor
    from src.storage import SupplyChainReport

logger = logging.getLogger(__name__)


# 报告产物目录：项目根/reports/supply_chain/
_REPORTS_ROOT = Path(__file__).parent.parent.parent / "reports"
_SUPPLY_CHAIN_DIR = _REPORTS_ROOT / "supply_chain"

# 报告保留数量上限（第一阶段用常量，不新增配置项）
_MAX_REPORTS = 200

# 彩色 emoji + 变体选择符：WeasyPrint 无法把彩色 emoji 位图（sbix/CBDT）嵌入 PDF，
# 路由到 Apple-Color-Emoji 字体时渲染成豆腐块（乱码）。仅剥掉装饰性 emoji，保留
# CJK / ①②③ / ≤ / μ / • / → / —— 等信息性字符。**PDF 渲染专用，不改 .md 原文**。
_EMOJI_STRIP_RE = re.compile(
    "[" "\U0001F1E6-\U0001F1FF"  # 区域指示符（旗帜）
    "\U0001F300-\U0001FAFF"      # 补充平面 emoji / 象形（📈🔥✅🎯…）
    "☀-➿"              # 杂项符号 & 丁巴符（⚠ ✂ ✏ ✅ …）
    "⬀-⯿"              # 补充符号象形 A
    "︀-️"              # 变体选择符 VS1-VS16
    "‍"                     # 零宽连接符 ZWJ
    "]+"
)


def strip_emoji_for_pdf(text: Optional[str]) -> str:
    """剥掉 PDF 渲染时无法呈现的彩色 emoji / 变体选择符（保留 CJK 与常用符号）。

    信息性字符（中文、①②③、≤、μm、•、→、—— 等）WeasyPrint 经 PingFang SC 能正常渲染，
    故保留；仅剥装饰性 emoji（警告语义由周围文字承担）。``None`` / 空串安全返回空串。
    """
    return _EMOJI_STRIP_RE.sub("", text or "")


_executor_instance: Optional["SupplyChainExecutor"] = None


class SupplyChainReportInputError(ValueError):
    """输入校验错误（分析主题为空等），endpoint 转 HTTP 400/422。"""


def get_supply_chain_report_dir() -> Path:
    """返回供应链报告目录，确保存在（Docker volume 子目录首次写入需 mkdir）。"""
    _SUPPLY_CHAIN_DIR.mkdir(parents=True, exist_ok=True)
    return _SUPPLY_CHAIN_DIR


def _get_executor() -> "SupplyChainExecutor":
    """获取（缓存的）SupplyChainExecutor 单例（复用问股工具集 + 供应链打分工具）。"""
    global _executor_instance
    if _executor_instance is None:
        from src.agent.factory import build_supply_chain_executor

        _executor_instance = build_supply_chain_executor(get_config())
    return _executor_instance


def build_supply_chain_user_message(topic: str, research_hint: Optional[str]) -> str:
    """组装本轮 user message（线索非空时注入一次性调查指令）。

    - 无线索：只发分析主题（行为与普通供应链报告一致）。
    - 有线索：把用户线索包装成高优先级调查目标（不代表事实）。
    """
    base = f"分析主题：\n{topic}"
    hint = (research_hint or "").strip()
    if not hint:
        return base
    return (
        f"{base}\n\n"
        "高优先级供应链线索（只对本轮报告生效，不代表事实）：\n"
        f"{hint}\n\n"
        "本轮必须围绕该线索执行：\n"
        "1. 主动搜索公告、财报、新闻、行业资料、上下游公司信息。\n"
        "2. 对关键说法至少做两类来源交叉验证；无法验证时标注“待核验”。\n"
        "3. 同时寻找支持、冲突、证伪信息。\n"
        "4. 把验证结果写入最终报告的“线索验证”部分。\n"
        "5. 说明该线索如何影响供应链层级排序、候选标的、瓶颈分和风险判断。"
    )


def _status_from_result(success: bool, markdown: str) -> str:
    """从 AgentResult 派生报告状态：success / partial / failed。

    - success=True → ``success``。
    - success=False 但有正文 → ``partial``（落盘可查）。
    - success=False 且无正文 → ``failed``。
    """
    if success:
        return "success"
    return "partial" if (markdown or "").strip() else "failed"


def _resolve_unique_report_id(ts: datetime) -> str:
    """生成唯一 report_id：``sc_{YYYYMMDDHHmm}_{seq}``（seq 从 1 起，碰撞递增）。

    始终带 ``_{seq}`` 后缀，与下载白名单 ``^sc_\\d{12}(_\\d+)?$`` 对齐；
    不把 topic slug 拼进 id（中文/空格进路径会增加安全成本）。
    """
    base = f"sc_{ts:%Y%m%d%H%M}"
    seq = 1
    while get_db().get_supply_chain_report(f"{base}_{seq}") is not None:
        seq += 1
    return f"{base}_{seq}"


class SupplyChainReportService:
    """供应链分析表单式报告编排服务（无状态，方法可独立调用）。"""

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate_report(
        self,
        raw_topic: str,
        raw_hint: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """生成一份供应链报告并落盘。返回 {report_id, status, markdown, ...}。"""
        topic = (raw_topic or "").strip()
        if not topic:
            raise SupplyChainReportInputError("分析主题不能为空")
        hint = (raw_hint or "").strip() or None

        report_id = _resolve_unique_report_id(datetime.now())
        report_dir = get_supply_chain_report_dir()
        md_path = report_dir / f"{report_id}.md"

        message = build_supply_chain_user_message(topic, hint)
        session_id = f"supply_chain_report:{report_id}"

        executor = _get_executor()
        result = executor.chat(
            message=message,
            session_id=session_id,
            progress_callback=progress_callback,
        )

        markdown = getattr(result, "content", "") or ""
        status = _status_from_result(bool(getattr(result, "success", False)), markdown)
        write_ok = False
        if markdown:
            try:
                md_path.write_text(markdown, encoding="utf-8")
                write_ok = True
            except OSError as exc:
                logger.error("[SupplyChainReport] 写报告文件失败 %s: %s", md_path, exc)

        result_error: Optional[str] = getattr(result, "error", None)
        if write_ok:
            get_db().save_supply_chain_report(
                report_id=report_id,
                topic=topic,
                research_hint=hint,
                md_path=str(md_path),
                status=status,
                total_steps=int(getattr(result, "total_steps", 0) or 0),
                total_tokens=int(getattr(result, "total_tokens", 0) or 0),
                provider=str(getattr(result, "provider", "") or ""),
                model=getattr(result, "model", None),
                error=result_error if status != "success" else None,
            )
            self._prune_and_clean_files(_MAX_REPORTS)

        if progress_callback:
            progress_callback(
                {
                    "type": "done",
                    "success": write_ok,
                    "report_id": report_id if write_ok else None,
                    "status": status,
                    "markdown": markdown,
                    "total_steps": int(getattr(result, "total_steps", 0) or 0),
                    "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
                    "provider": str(getattr(result, "provider", "") or ""),
                    "error": result_error if not getattr(result, "success", False) else None,
                }
            )

        return {
            "report_id": report_id if write_ok else None,
            "topic": topic,
            "research_hint": hint,
            "status": status,
            "markdown": markdown,
            "md_path": str(md_path) if write_ok else None,
            "total_steps": int(getattr(result, "total_steps", 0) or 0),
            "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
            "provider": str(getattr(result, "provider", "") or ""),
            "model": getattr(result, "model", None),
            "error": result_error if not getattr(result, "success", False) else None,
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_reports(self, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """分页列表（不含 Markdown 正文，仅元数据）。"""
        rows, total = get_db().get_supply_chain_reports(offset=offset, limit=limit)
        return [r.to_dict() for r in rows], total

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """单条报告详情（含 Markdown 正文，从文件读取）。"""
        record = get_db().get_supply_chain_report(report_id)
        if record is None:
            return None
        data = record.to_dict()
        markdown = ""
        try:
            md_path = Path(record.md_path)
            if md_path.exists():
                markdown = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[SupplyChainReport] 读取报告正文失败 %s: %s", record.md_path, exc)
        data["markdown"] = markdown
        return data

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_report(self, report_id: str) -> bool:
        """删除报告（元数据 + .md + .pdf 文件）。"""
        paths = get_db().delete_supply_chain_report(report_id)
        if paths is None:
            return False
        for key in ("md_path", "pdf_path"):
            p = paths.get(key)
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("[SupplyChainReport] 删除文件失败 %s: %s", p, exc)
        logger.info("[SupplyChainReport] 已删除报告 %s", report_id)
        return True

    # ------------------------------------------------------------------
    # PDF（复用共享 md2pdf）
    # ------------------------------------------------------------------

    def get_pdf_path(self, report_id: str) -> Optional[str]:
        """返回报告 PDF 路径；未生成则触发惰性生成。"""
        record = get_db().get_supply_chain_report(report_id)
        if record is None:
            return None
        if record.pdf_path and Path(record.pdf_path).exists():
            return record.pdf_path
        return self._generate_pdf(record)

    def _generate_pdf(self, record: "SupplyChainReport") -> Optional[str]:
        """惰性生成 PDF（复用 src/md2pdf.py）。"""
        try:
            from src.md2pdf import markdown_to_pdf_file
        except ImportError:
            logger.warning("[SupplyChainReport] md2pdf 不可用，PDF 暂不可用")
            return None

        md_path = Path(record.md_path)
        if not md_path.exists():
            return None
        # PDF 渲染前剥彩色 emoji（WeasyPrint 无法嵌入彩色 emoji 位图，会渲染成豆腐块）；
        # .md 原文不动，Web/Markdown 视图仍显示 emoji。
        markdown = strip_emoji_for_pdf(md_path.read_text(encoding="utf-8"))
        pdf_path = str(md_path.with_suffix(".pdf"))

        result_path = markdown_to_pdf_file(markdown, pdf_path)
        if result_path:
            get_db().set_supply_chain_pdf_path(record.id, result_path)
            return result_path
        return None

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _prune_and_clean_files(self, max_reports: int) -> None:
        """清理超额报告：删元数据（事务内）+ 删文件（事务外）。"""
        if max_reports <= 0:
            return
        pruned = get_db().prune_supply_chain_reports(max_reports)
        for paths in pruned:
            for key in ("md_path", "pdf_path"):
                p = paths.get(key)
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning("[SupplyChainReport] 清理删除文件失败 %s: %s", p, exc)
        if pruned:
            logger.info("[SupplyChainReport] 清理超额报告 %d 份", len(pruned))


# 模块级单例（与现有 service 风格一致）
supply_chain_report_service = SupplyChainReportService()
