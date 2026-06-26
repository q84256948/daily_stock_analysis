# -*- coding: utf-8 -*-
"""政策与公告双维度排雷编排服务（A 股）。

职责（编排层，不含 LLM/数据获取细节）：
1. A 股代码校验与归一化（强制 cn 市场，拒绝港股/美股）。
2. 调用 :class:`PolicyMinesweeperExecutor` 生成报告（α/β 并行 → Ω 综合 + 降级）。
3. 报告存盘：Markdown 写文件（``reports/policy_minesweeper/``）+ 元数据写 SQLite。
4. best-effort 从正文 scorecard banner 解析 composite_score/verdict/confidence（可能为 NULL）。
5. 超额清理（删元数据同步删文件）。
6. 列表/详情/删除代理 + PDF 惰性生成入口（复用共享 ``src/md2pdf.py``）。

不直接跑 ReAct 循环（在 executor）；不直接做 PDF 渲染（在 md2pdf）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import get_config
from src.services.stock_code_utils import normalize_code
from src.storage import get_db

logger = logging.getLogger(__name__)


# 报告产物目录：项目根/reports/policy_minesweeper/
_REPORTS_ROOT = Path(__file__).parent.parent.parent / "reports"
_POLICY_MINESWEEPER_DIR = _REPORTS_ROOT / "policy_minesweeper"

# report_id 格式：{6位A股代码}_{YYYYMMDDHHmm}（与下载白名单 ^\d{6}_\d{12}(_\d+)?$ 对齐）
_REPORT_ID_PATTERN = "{code}_{ts:%Y%m%d%H%M}"

_executor_instance: Optional[Any] = None

# best-effort 解析 scorecard to_markdown 的 banner 行（emoji + **label**　综合分 **N**　置信度 **N%**）
_VERDICT_LABELS = ("强利好", "中等利好", "中性", "中等利空", "强利空")
_RE_VERDICT = re.compile(r"\*\*(" + "|".join(_VERDICT_LABELS) + r")\*\*")
_RE_COMPOSITE = re.compile(r"综合分\s*\*\*(-?\d+)\*\*")
_RE_CONFIDENCE = re.compile(r"置信度\s*\*\*(\d+)%\*\*")


class PolicyMinesweeperInputError(ValueError):
    """输入校验错误（非 A 股、格式非法等），endpoint 转 HTTP 400。"""


def get_policy_minesweeper_dir() -> Path:
    """返回排雷报告目录，确保存在（Docker volume 子目录首次写入需 mkdir）。"""
    _POLICY_MINESWEEPER_DIR.mkdir(parents=True, exist_ok=True)
    return _POLICY_MINESWEEPER_DIR


def _max_reports() -> int:
    """保留报告数量上限（默认 200）。"""
    try:
        return int(getattr(get_config(), "policy_minesweeper_max_reports", 200))
    except Exception:
        return 200


def _lookup_stock_name(code: str) -> str:
    """反查股票中文名（raw_name 缺省时用）。失败返回空串，不阻塞生成。"""
    try:
        from src.agent.tools.data_tools import _get_fetcher_manager

        quote = _get_fetcher_manager().get_realtime_quote(code)
        if quote and quote.name:
            return str(quote.name).strip()
    except Exception as exc:
        logger.debug("[PolicyMinesweeper] 反查股票名称失败 %s: %s", code, exc)
    return ""


def _resolve_unique_report_id(base_id: str) -> str:
    """确保 report_id 唯一：若 base_id 已存在，追加 _1/_2/... 后缀（防 merge 覆盖致文件孤儿）。"""
    report_id = base_id
    seq = 1
    while get_db().get_policy_minesweeper_report(report_id) is not None:
        report_id = f"{base_id}_{seq}"
        seq += 1
    return report_id


def _get_executor() -> Any:
    """获取（缓存的）PolicyMinesweeperExecutor 单例。"""
    global _executor_instance
    if _executor_instance is None:
        from src.agent.factory import build_policy_minesweeper_executor

        _executor_instance = build_policy_minesweeper_executor()
    return _executor_instance


def normalize_a_share(raw_code: str) -> str:
    """归一化并校验为 A 股代码（6 位纯数字）。非 A 股抛异常（endpoint 转 400）。"""
    if not raw_code or not str(raw_code).strip():
        raise PolicyMinesweeperInputError("股票代码不能为空")

    normalized = normalize_code(str(raw_code).strip())
    if not normalized:
        raise PolicyMinesweeperInputError(f"无法识别的股票代码：{raw_code}")

    if not (normalized.isdigit() and len(normalized) == 6):
        raise PolicyMinesweeperInputError(
            f"政策与公告排雷当前仅支持 A 股，代码 {raw_code}（归一化为 {normalized}）非 A 股"
        )
    return normalized


def extract_score(markdown: str) -> Dict[str, Any]:
    """best-effort 从报告正文解析综合分/等级/置信度。解析不到返回 None 值。"""
    if not markdown:
        return {"composite_score": None, "verdict": None, "confidence": None}
    verdict = None
    m_verdict = _RE_VERDICT.search(markdown)
    if m_verdict:
        verdict = m_verdict.group(1)
    m_comp = _RE_COMPOSITE.search(markdown)
    composite = int(m_comp.group(1)) if m_comp else None
    m_conf = _RE_CONFIDENCE.search(markdown)
    confidence = int(m_conf.group(1)) if m_conf else None
    return {"composite_score": composite, "verdict": verdict, "confidence": confidence}


class PolicyMinesweeperService:
    """政策与公告双维度排雷编排服务（无状态，方法可独立调用）。"""

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate_report(
        self,
        raw_code: str,
        raw_name: Optional[str] = None,
        horizon: str = "medium",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """生成一份排雷报告并落盘。返回 {report_id, status, markdown, ...}。"""
        code = normalize_a_share(raw_code)
        name = (raw_name or "").strip()
        if not name:
            name = _lookup_stock_name(code) or code

        report_id = _REPORT_ID_PATTERN.format(code=code, ts=datetime.now())
        report_id = _resolve_unique_report_id(report_id)
        report_dir = get_policy_minesweeper_dir()
        md_path = report_dir / f"{report_id}.md"

        executor = _get_executor()
        result = executor.generate(
            stock_code=code,
            stock_name=name,
            horizon=horizon,
            progress_callback=progress_callback,
        )

        markdown = result.markdown or ""
        score = extract_score(markdown)
        write_ok = False
        if markdown:
            try:
                md_path.write_text(markdown, encoding="utf-8")
                write_ok = True
            except OSError as exc:
                logger.error("[PolicyMinesweeper] 写报告文件失败 %s: %s", md_path, exc)

        if write_ok:
            get_db().save_policy_minesweeper_report(
                report_id=report_id,
                stock_code=code,
                stock_name=name,
                md_path=str(md_path),
                status=result.status,
                horizon=horizon,
                alpha_ok=result.alpha_ok,
                beta_ok=result.beta_ok,
                omega_ok=result.omega_ok,
                composite_score=score["composite_score"],
                verdict=score["verdict"],
                confidence=score["confidence"],
                total_steps=result.total_steps,
                total_tokens=result.total_tokens,
                provider=result.provider,
            )
            self._prune_and_clean_files(_max_reports())

        if progress_callback:
            progress_callback(
                {
                    "type": "done",
                    "report_id": report_id if write_ok else None,
                    "status": result.status,
                    "markdown": markdown,
                    "error": result.error if not result.success else None,
                }
            )

        return {
            "report_id": report_id if write_ok else None,
            "stock_code": code,
            "stock_name": name,
            "status": result.status,
            "horizon": horizon,
            "alpha_ok": result.alpha_ok,
            "beta_ok": result.beta_ok,
            "omega_ok": result.omega_ok,
            "composite_score": score["composite_score"],
            "verdict": score["verdict"],
            "confidence": score["confidence"],
            "markdown": markdown,
            "md_path": str(md_path) if write_ok else None,
            "total_steps": result.total_steps,
            "total_tokens": result.total_tokens,
            "provider": result.provider,
            "error": result.error if not result.success else None,
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_reports(
        self, limit: int = 50, offset: int = 0, stock_code: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页列表（不含 Markdown 正文，仅元数据）。"""
        rows, total = get_db().get_policy_minesweeper_reports(
            stock_code=stock_code, offset=offset, limit=limit
        )
        return [r.to_dict() for r in rows], total

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """单条报告详情（含 Markdown 正文，从文件读取）。"""
        record = get_db().get_policy_minesweeper_report(report_id)
        if record is None:
            return None
        data = record.to_dict()
        markdown = ""
        try:
            md_path = Path(record.md_path)
            if md_path.exists():
                markdown = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[PolicyMinesweeper] 读取报告正文失败 %s: %s", record.md_path, exc)
        data["markdown"] = markdown
        return data

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_report(self, report_id: str) -> bool:
        """删除报告（元数据 + .md + .pdf 文件）。"""
        paths = get_db().delete_policy_minesweeper_report(report_id)
        if paths is None:
            return False
        for key in ("md_path", "pdf_path"):
            p = paths.get(key)
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("[PolicyMinesweeper] 删除文件失败 %s: %s", p, exc)
        logger.info("[PolicyMinesweeper] 已删除报告 %s", report_id)
        return True

    # ------------------------------------------------------------------
    # PDF（复用共享 md2pdf）
    # ------------------------------------------------------------------

    def get_pdf_path(self, report_id: str) -> Optional[str]:
        """返回报告 PDF 路径；未生成则触发惰性生成。"""
        record = get_db().get_policy_minesweeper_report(report_id)
        if record is None:
            return None
        if record.pdf_path and Path(record.pdf_path).exists():
            return record.pdf_path
        return self._generate_pdf(record)

    def _generate_pdf(self, record: Any) -> Optional[str]:
        """惰性生成 PDF（复用 src/md2pdf.py）。"""
        try:
            from src.md2pdf import markdown_to_pdf_file
        except ImportError:
            logger.warning("[PolicyMinesweeper] md2pdf 不可用，PDF 暂不可用")
            return None

        md_path = Path(record.md_path)
        if not md_path.exists():
            return None
        markdown = md_path.read_text(encoding="utf-8")
        pdf_path = str(md_path.with_suffix(".pdf"))

        result_path = markdown_to_pdf_file(markdown, pdf_path)
        if result_path:
            get_db().set_policy_minesweeper_pdf_path(record.id, result_path)
            return result_path
        return None

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def _prune_and_clean_files(self, max_reports: int) -> None:
        """清理超额报告：删元数据（事务内）+ 删文件（事务外）。"""
        if max_reports <= 0:
            return
        pruned = get_db().prune_policy_minesweeper_reports(max_reports)
        for paths in pruned:
            for key in ("md_path", "pdf_path"):
                p = paths.get(key)
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning("[PolicyMinesweeper] 清理删除文件失败 %s: %s", p, exc)
        if pruned:
            logger.info("[PolicyMinesweeper] 清理超额报告 %d 份", len(pruned))


# 模块级单例（与现有 service 风格一致）
policy_minesweeper_service = PolicyMinesweeperService()
