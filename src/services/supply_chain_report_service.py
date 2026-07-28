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

# 共享 emoji 剥离函数从 src.md2pdf 导入，PDF 渲染统一在那里处理。
# （按 docs/pdf-generation-unification-plan.md §6.4：原 supply_chain 局部 strip_emoji_for_pdf
# 与 _EMOJI_STRIP_RE 已下沉到 src/md2pdf.py，本 service 不再重复定义。）

# 保留向后兼容 re-export：旧 import 路径仍可工作（业务代码、测试可能仍在用）。
from src.md2pdf import strip_emoji_for_pdf  # noqa: E402,F401  (re-export for back-compat)

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

    # [v3 PR-C] 灰度开关：默认关闭，PR-C 上线后逐步开启
    _DEEP_DIVE_ENABLED_ENV = "SERENITY_DEEP_DIVE_V3_ENABLED"

    @classmethod
    def _is_deep_dive_enabled(cls) -> bool:
        """从环境变量读取灰度开关（默认 False）。"""
        import os

        val = os.environ.get(cls._DEEP_DIVE_ENABLED_ENV, "false").strip().lower()
        return val in {"1", "true", "yes", "on"}

    def _extract_deep_dive_section(self, markdown: str) -> "Optional[Dict[str, Any]]":
        """[v3 PR-C] 从 LLM 输出的完整报告中提取 §6-§10 + 脚注 段。

        灰度关闭 / 段不存在 → 返回 None。
        """
        if not self._is_deep_dive_enabled():
            return None
        try:
            from src.services.supply_chain.deep_dive_renderer import (
                extract_deep_dive_section_from_markdown,
            )

            section = extract_deep_dive_section_from_markdown(markdown or "")
            if not section:
                return None
            # 浅解析：直接把 §6-§10 段原文存到 deep_dive_json 中作为 backup；
            # 完整的 SupplyChainDeepDiveV3 构造由 executor 解析后传入（PR-C+ 增强预留）。
            return {"_raw_markdown_section": section}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[SupplyChainReport v3] extract_deep_dive 失败: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate_report(
        self,
        raw_topic: str,
        raw_hint: Optional[str] = None,
        raw_code: Optional[str] = None,
        raw_name: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """生成一份供应链报告并落盘。返回 {report_id, status, markdown, ...}。

        可选绑定单股（按 docs/pdf-download-filename-plan.md §供应链报告边界）：
        - ``raw_code``：6 位 A 股代码（自动归一化剥后缀 / 前缀）
        - ``raw_name``：股票中文名
        两者至少给一个时，PDF 文件名遵循 ``股票名（代码）报告类型YYYYMMDD.pdf``；
        都为空时仍走主题型命名（向后兼容历史报告）。
        """
        topic = (raw_topic or "").strip()
        if not topic:
            raise SupplyChainReportInputError("分析主题不能为空")
        hint = (raw_hint or "").strip() or None
        # 单股代码归一化（与 deep_research / policy_minesweeper 一致）
        code: Optional[str] = None
        if raw_code:
            try:
                from data_provider.base import normalize_stock_code
            except ImportError:
                normalize_stock_code = None  # type: ignore[assignment]
            normalized = (
                normalize_stock_code(str(raw_code).strip())
                if normalize_stock_code is not None
                else str(raw_code).strip()
            )
            if normalized and normalized.isdigit() and len(normalized) == 6:
                code = normalized
            elif normalized:
                # 非 A 股代码：留空（fallback 主题型）
                logger.warning(
                    "[SupplyChainReport] stock_code %r 归一化后非 6 位 A 股，fallback 主题型",
                    raw_code,
                )
        name = (str(raw_name).strip() if raw_name else "") or None
        # 名称未提供时，用代码兜底（让 helper 渲染为 ``600519（600519）...``）
        if code and not name:
            name = code

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
        # [v3 PR-C] 从 LLM 输出中提取 §6-§10 深度小节段（灰度开关控制）
        deep_dive_data = self._extract_deep_dive_section(markdown)
        import json as _json

        deep_dive_json: Optional[str] = (
            _json.dumps(deep_dive_data, ensure_ascii=False)
            if deep_dive_data is not None
            else None
        )
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
                stock_code=code,
                stock_name=name,
                md_path=str(md_path),
                status=status,
                total_steps=int(getattr(result, "total_steps", 0) or 0),
                total_tokens=int(getattr(result, "total_tokens", 0) or 0),
                provider=str(getattr(result, "provider", "") or ""),
                model=getattr(result, "model", None),
                error=result_error if status != "success" else None,
                deep_dive_json=deep_dive_json,
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
                    "error": result_error
                    if not getattr(result, "success", False)
                    else None,
                }
            )

        return {
            "report_id": report_id if write_ok else None,
            "topic": topic,
            "research_hint": hint,
            "stock_code": code,
            "stock_name": name,
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

    def list_reports(
        self, limit: int = 50, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
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
            logger.warning(
                "[SupplyChainReport] 读取报告正文失败 %s: %s", record.md_path, exc
            )
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
        """惰性生成 PDF（复用 src/md2pdf.py）。

        彩色 emoji 剥离由 ``src.md2pdf`` 内部统一处理（按
        docs/pdf-generation-unification-plan.md §6.4 下沉），本 service 不再
        局部剥离，避免与共享渲染器重复。``.md`` 原文不被修改。
        """
        try:
            from src.md2pdf import markdown_to_pdf_file
        except ImportError:
            logger.warning("[SupplyChainReport] md2pdf 不可用，PDF 暂不可用")
            return None

        md_path = Path(record.md_path)
        if not md_path.exists():
            return None
        # 直接读取 markdown 原文传给共享渲染器（emoji 剥离由 md2pdf 内部处理）
        markdown = md_path.read_text(encoding="utf-8")
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
                        logger.warning(
                            "[SupplyChainReport] 清理删除文件失败 %s: %s", p, exc
                        )
        if pruned:
            logger.info("[SupplyChainReport] 清理超额报告 %d 份", len(pruned))


# 模块级单例（与现有 service 风格一致）
supply_chain_report_service = SupplyChainReportService()
