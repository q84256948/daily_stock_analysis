# -*- coding: utf-8 -*-
"""供应链双源校验层（KISS · 纯逻辑判定 + fail-open IO 探针）。

职责：对供应链报告中的「公司 / 板块归属」类事实，分别取东方财富与同花顺
两类来源的结构化证据，按统一决策表产出 ``status`` / ``confidence``，让报告
不能把单源线索写成双源确认。

设计要点（高内聚低耦合，镜像 :mod:`data_provider.cross_source_validator`）：
- 本模块**只做判定**，判定逻辑全部是纯函数（``_judge_*`` / ``normalize_*``），
  无副作用、无网络，易做 100% 单测。
- IO（取板块 / 成分股）由调用方注入的 ``SupplyChainSourceProbe`` 负责，通过
  Protocol 解耦 —— 换源 / 测试注入 fake 都不改本模块。
- ``SupplyChainCrossSourceValidator.verify`` 编排「归一 → 收集 → 判定」，
  收集时**逐源 fail-open**：单源异常 / 不可用绝不拖垮另一源（"未核验"语义，
  不是"否定"）。
- 非 A 股（港股 / 美股 / 无法归一到 6 位代码）直接 ``not_applicable``，不联网。

状态语义（``status``）：
- ``confirmed``     东财 + 同花顺均命中目标公司
- ``partial``       仅一源命中（另一源不可用 / 未定位到相关板块）
- ``conflict``      两源均可用、均定位到相关板块，但对目标公司归属相反
- ``unverified``    两源均不可用，或均可用但都未命中
- ``not_applicable``非 A 股

置信度语义（``confidence``）：
- ``high``   双源命中（``confirmed``）
- ``medium`` 单源命中（``partial``）
- ``low``    冲突 / 双源缺失 / 非适用范围

对应方案 ``docs/supply-chain-cross-source-validation-plan.md``。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Sequence, Tuple

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 归一化纯函数
# ------------------------------------------------------------------

# A 股 6 位代码：允许 SH/SZ/BJ 前缀或 .SH/.SZ/.BJ 后缀，内部归一为 6 位。
_ASHARE_PREFIX_RE = re.compile(r"^(?:sh|sz|bj)", re.IGNORECASE)
_ASHARE_SUFFIX_RE = re.compile(r"\.(?:sh|sz|bj)$", re.IGNORECASE)
_SIX_DIGIT_RE = re.compile(r"^\d{6}$")

# A 股首位合法数字：6xx 沪 / 0xx·3xx 深 / 4xx·8xx·9xx 北交所及老三板。
_ASHARE_FIRST_DIGITS = frozenset("034689")

# 名称 / 板块名标准化时剥离的噪声字符（空白 + 常见分隔 / 标点）。
_NAME_NOISE_RE = re.compile(r"[\s\-_/\\,，。·、()（）]+")


def normalize_a_share_code(code: Any) -> Optional[str]:
    """把股票代码归一为 A 股 6 位字符串。

    接受 ``300750`` / ``sz300750`` / ``300750.SZ`` / ``SH600519`` 等写法；
    港股（5 位）/ 美股（字母）/ 非法格式 / 非 A 股首位 → 返回 ``None``。
    """
    if not isinstance(code, str):
        return None
    s = code.strip()
    s = _ASHARE_PREFIX_RE.sub("", s)
    s = _ASHARE_SUFFIX_RE.sub("", s)
    if not _SIX_DIGIT_RE.match(s):
        return None
    if s[0] not in _ASHARE_FIRST_DIGITS:
        return None
    return s


def normalize_name(name: Any) -> str:
    """标准化名称 / 板块名：去首尾空白（含全角空格）+ 去常见分隔标点。"""
    if not isinstance(name, str):
        return ""
    s = name.strip().replace("　", "")
    return _NAME_NOISE_RE.sub("", s)


# ------------------------------------------------------------------
# 匹配 / 重合度纯函数
# ------------------------------------------------------------------

# 板块名匹配等级（高 → 低）。
BOARD_MATCH_EXACT = "exact"
BOARD_MATCH_CONTAINS = "contains"


def board_match_level(keyword: Any, board_name: Any) -> Optional[str]:
    """判定 keyword 与板块名的匹配等级。

    返回 ``exact``（标准化后相等）/ ``contains``（互为子串）/ ``None``（不匹配）。
    """
    kw = normalize_name(keyword)
    bn = normalize_name(board_name)
    if not kw or not bn:
        return None
    if kw == bn:
        return BOARD_MATCH_EXACT
    if kw in bn or bn in kw:
        return BOARD_MATCH_CONTAINS
    return None


def find_matched_boards(keyword: Any, board_names: Sequence[Any]) -> Tuple[str, ...]:
    """从板块名列表中筛出与 keyword 匹配的板块名（保持顺序、去重）。"""
    seen: list[str] = []
    for name in board_names or ():
        name_str = str(name).strip()
        if not name_str:
            continue
        if board_match_level(keyword, name_str) is not None and name_str not in seen:
            seen.append(name_str)
    return tuple(seen)


def code_in_constituents(code: str, constituents: Sequence[Any]) -> bool:
    """目标代码是否出现在成分股集合中（成分股逐个归一后比较，健壮）。"""
    if not code:
        return False
    for raw in constituents or ():
        if normalize_a_share_code(raw) == code:
            return True
    return False


def constituent_overlap_ratio(
    a: Sequence[Any], b: Sequence[Any]
) -> float:
    """两个成分股集合的 Jaccard 重合度（交集 / 并集）。

    任一为空且另一非空时并集非空但交集为空 → ``0.0``；双空 → ``0.0``。
    """
    set_a = {norm for raw in (a or ()) if (norm := normalize_a_share_code(raw))}
    set_b = {norm for raw in (b or ()) if (norm := normalize_a_share_code(raw))}
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def compute_matched_by(
    code: str,
    em: "SourceEvidence",
    ths: "SourceEvidence",
    board_hint: Any,
) -> Tuple[str, ...]:
    """汇总命中的证据维度：``code``（代码入成分股）/ ``board_name``（板块名命中）。"""
    dims: list[str] = []
    all_constituents = tuple(em.constituents) + tuple(ths.constituents)
    if code_in_constituents(code, all_constituents):
        dims.append("code")
    if board_hint:
        for board in tuple(em.boards) + tuple(ths.boards):
            if board_match_level(board_hint, board) is not None:
                dims.append("board_name")
                break
    return tuple(dims)


# ------------------------------------------------------------------
# 数据结构（不可变）
# ------------------------------------------------------------------
@dataclass(frozen=True)
class SourceEvidence:
    """单个数据源对一次校验的结构化证据。"""

    source: str  # "eastmoney" | "akshare_ths" | ...
    available: bool  # 源是否可用（响应了 / 解析成功）
    matched: bool  # 目标公司是否命中（代码入成分股）
    boards: Tuple[str, ...] = ()  # 命中（与关键词匹配）的板块名
    constituents: Tuple[str, ...] = ()  # 命中板块的成分股代码
    error: Optional[str] = None  # 失败摘要（成功时为 None）

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "available": self.available,
            "matched": self.matched,
            "boards": list(self.boards),
            "constituents": list(self.constituents),
            "source": self.source,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class VerificationResult:
    """双源校验结果（不可变）。"""

    stock_code: str
    stock_name: str
    scope: str  # "a_share" | "not_applicable"
    status: str  # confirmed | partial | conflict | unverified | not_applicable
    confidence: str  # high | medium | low
    eastmoney: SourceEvidence
    ths: SourceEvidence
    overlap_ratio: float
    matched_by: Tuple[str, ...]
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "scope": self.scope,
            "status": self.status,
            "confidence": self.confidence,
            "eastmoney": self.eastmoney.to_dict(),
            "ths": self.ths.to_dict(),
            "overlap": {
                "constituent_overlap_ratio": round(self.overlap_ratio, 4),
                "matched_by": list(self.matched_by),
            },
            "note": self.note,
        }


# ------------------------------------------------------------------
# SupplyChainSourceProbe Protocol（N 源可插拔）
# ------------------------------------------------------------------
class SupplyChainSourceProbe(Protocol):
    """数据源探针协议。实现 ``probe`` 即可被 validator 调用。"""

    name: str

    def probe(self, code: str, name: str, keyword: str) -> SourceEvidence:
        """读取某股票在某关键词（板块 / 主题）下的归属证据。

        失败应在内部捕获并返回 ``available=False`` 的证据（fail-open），不抛异常。
        """
        ...


# ------------------------------------------------------------------
# 判定纯函数（决策表）
# ------------------------------------------------------------------
def judge_verification(
    code: str,
    name: str,
    em: SourceEvidence,
    ths: SourceEvidence,
    board_hint: Any,
) -> VerificationResult:
    """按决策表判定双源校验状态（纯函数，无副作用）。

    决策表（见方案「状态决策」）：

    | 条件 | status | confidence |
    | --- | --- | --- |
    | 东财和同花顺均命中目标公司 | confirmed | high |
    | 两源均可用、均定位到相关板块，归属相反 | conflict | low |
    | 仅一源命中（另一源不可用 / 未定位到板块） | partial | medium |
    | 两源均不可用，或均可用但都未命中 | unverified | low |
    """
    overlap = constituent_overlap_ratio(em.constituents, ths.constituents)
    matched_by = compute_matched_by(code, em, ths, board_hint)

    em_hit = em.available and em.matched
    ths_hit = ths.available and ths.matched
    em_found = em.available and len(em.boards) > 0
    ths_found = ths.available and len(ths.boards) > 0

    if em_hit and ths_hit:
        return _result(
            code, name, "confirmed", "high", em, ths, overlap, matched_by,
            "东方财富和同花顺均支持该公司属于相关板块，双源确认",
        )

    if em.available and ths.available:
        if not em_hit and not ths_hit:
            return _result(
                code, name, "unverified", "low", em, ths, overlap, matched_by,
                "东方财富和同花顺均可用，但两源均未命中目标公司，待核验",
            )
        if em_found and ths_found:
            return _result(
                code, name, "conflict", "low", em, ths, overlap, matched_by,
                "东方财富/同花顺口径冲突：两源均定位到相关板块，但对目标公司归属不一致",
            )
        return _result(
            code, name, "partial", "medium", em, ths, overlap, matched_by,
            "单源支持，待另一源核验",
        )

    if em_hit or ths_hit:
        return _result(
            code, name, "partial", "medium", em, ths, overlap, matched_by,
            "单源支持（另一源不可用），待另一源核验",
        )

    return _result(
        code, name, "unverified", "low", em, ths, overlap, matched_by,
        "东方财富和同花顺均不可用或无命中，待核验",
    )


def _not_applicable_result(stock_code: Any, stock_name: Any) -> VerificationResult:
    """非 A 股：直接返回 not_applicable，不联网。"""
    empty_em = SourceEvidence("eastmoney", available=False, matched=False)
    empty_ths = SourceEvidence("ths", available=False, matched=False)
    return VerificationResult(
        stock_code=str(stock_code or ""),
        stock_name=str(stock_name or ""),
        scope="not_applicable",
        status="not_applicable",
        confidence="low",
        eastmoney=empty_em,
        ths=empty_ths,
        overlap_ratio=0.0,
        matched_by=(),
        note="非 A 股标的或无法归一到 A 股 6 位代码，双源校验不适用",
    )


def _result(
    code: str,
    name: str,
    status: str,
    confidence: str,
    em: SourceEvidence,
    ths: SourceEvidence,
    overlap: float,
    matched_by: Tuple[str, ...],
    note: str,
) -> VerificationResult:
    return VerificationResult(
        stock_code=code,
        stock_name=name,
        scope="a_share",
        status=status,
        confidence=confidence,
        eastmoney=em,
        ths=ths,
        overlap_ratio=overlap,
        matched_by=matched_by,
        note=note,
    )


# ------------------------------------------------------------------
# fail-open IO 探针（实现 Protocol）
# ------------------------------------------------------------------
class EastMoneyProbe:
    """东方财富探针：复用 ``ConceptBoardProvider``（akshare 东财概念板块）。"""

    name = "eastmoney"

    def __init__(self, provider: Any = None) -> None:
        # provider 注入用于测试；运行时懒加载单例，避免 import 期触发 akshare。
        self._provider = provider

    def _resolve(self) -> Any:
        if self._provider is not None:
            return self._provider
        from data_provider.supply_chain.concept_board import get_concept_board_provider

        return get_concept_board_provider()

    def probe(self, code: str, name: str, keyword: str) -> SourceEvidence:
        provider = self._resolve()
        boards = provider.get_concept_boards() or []
        matched_boards = [
            b for b in boards
            if board_match_level(keyword, b.get("name", "")) is not None
        ]
        constituents: list[str] = []
        for board in matched_boards:
            constituents.extend(provider.get_concept_constituents(board.get("name", "")) or [])
        return SourceEvidence(
            source=self.name,
            available=True,
            matched=code_in_constituents(code, constituents),
            boards=tuple(b.get("name", "") for b in matched_boards),
            constituents=tuple(constituents),
        )


class ThsAkshareProbe:
    """同花顺探针（akshare 概念列表 + 同花顺概念详情页 best-effort）。

    来源标记 ``akshare_ths``。实现说明：akshare 仅有 ``stock_board_concept_name_ths()``
    （概念列表，列 ``name`` / ``code``），**没有**概念成分股接口；因此成分股走同花顺
    概念详情页 ``q.10jqka.com.cn/gn/detail/code/{code}/``（GBK）正则解析（与东财热点
    provider 同源、经验证可用）。``http_get`` 可注入，便于离线单测；公开页结构变化 /
    抓取失败 → fail-open 返回 ``available=False``，不抛异常。

    iFinD MCP 当前仅覆盖估值 / 财务数值锚点，不支持板块成分股结构化查询；如需 iFinD
    优先，可新增实现 ``SupplyChainSourceProbe`` 的 ``IfindBoardProbe`` 注入 validator。
    """

    name = "akshare_ths"

    # 同花顺概念详情页（分页 ``/order/desc/page/{page}/``，成分股由正则 >(\d{6})< 解析）。
    _THS_DETAIL_URL = "http://q.10jqka.com.cn/gn/detail/code/{code}/order/desc/page/{page}/"
    _THS_CODE_RE = re.compile(r">(\d{6})<")
    _DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    # 同花顺概念页每页约 11 只，单概念成分股封顶翻页数（防异常页无限翻）。
    _MAX_THS_PAGES = 10

    def __init__(self, akshare_module: Any = None, http_get: Any = None) -> None:
        # akshare_module / http_get 注入用于测试（duck-typed fake），避免真实网络。
        # http_get 签名: ``http_get(concept_code: str, page: int) -> str(html)``。
        self._ak = akshare_module
        self._http_get = http_get

    def _resolve_akshare(self) -> Any:
        if self._ak is not None:
            return self._ak
        try:
            import akshare as ak

            return ak
        except ImportError:
            return None

    def _resolve_http_get(self) -> Any:
        if self._http_get is not None:
            return self._http_get

        def _real_get(concept_code: str, page: int) -> str:
            import requests

            url = self._THS_DETAIL_URL.format(code=concept_code, page=page)
            resp = requests.get(url, headers={"User-Agent": self._DEFAULT_UA}, timeout=8)
            return resp.content.decode("gbk", errors="ignore")

        return _real_get

    @staticmethod
    def _concept_pairs(name_df: Any) -> list[tuple[str, str]]:
        """从同花顺概念列表 DataFrame 提取 ``[(概念名, 概念代码), ...]``。

        akshare 返回列 ``['name', 'code']``（小写）；列名漂移时返回空（fail-open）。
        """
        if name_df is None:
            return []
        try:
            cols = {str(c).lower(): str(c) for c in name_df.columns}
        except AttributeError:
            return []
        name_col = cols.get("name") or cols.get("概念名称")
        code_col = cols.get("code") or cols.get("代码")
        if not name_col or not code_col:
            return []
        # 注意：akshare 返回 pandas Series，不能用 ``series or []``（truth 值歧义）。
        raw_names = name_df.get(name_col)
        raw_codes = name_df.get(code_col)
        names = list(raw_names) if raw_names is not None else []
        codes = list(raw_codes) if raw_codes is not None else []
        return [
            (str(n).strip(), str(c).strip())
            for n, c in zip(names, codes)
            if str(n).strip() and str(c).strip()
        ]

    def probe(self, code: str, name: str, keyword: str) -> SourceEvidence:
        ak = self._resolve_akshare()
        if ak is None:
            return SourceEvidence(
                source=self.name,
                available=False,
                matched=False,
                error="akshare 未安装，同花顺概念数据不可用",
            )
        pairs = self._concept_pairs(ak.stock_board_concept_name_ths())
        matched_concepts = [
            (n, c) for n, c in pairs if board_match_level(keyword, n) is not None
        ]
        http_get = self._resolve_http_get()
        constituents: list[str] = []
        for concept_name, concept_code in matched_concepts:
            # 翻页直到空页（或封顶），确保成分股完整、减少因只取首页造成的假冲突。
            for page in range(1, self._MAX_THS_PAGES + 1):
                try:
                    html = http_get(concept_code, page)
                except Exception as exc:  # noqa: BLE001 — 单页抓取失败不拖垮其它
                    logger.debug(
                        "[SupplyChainCrossValidate] THS scrape %s p%d failed: %s",
                        concept_code, page, exc,
                    )
                    break
                page_codes = self._THS_CODE_RE.findall(html or "")
                if not page_codes:
                    break  # 空页 = 该概念成分股已取完
                constituents.extend(page_codes)
        return SourceEvidence(
            source=self.name,
            available=True,
            matched=code_in_constituents(code, constituents),
            boards=tuple(n for n, _ in matched_concepts),
            constituents=tuple(constituents),
        )


# ------------------------------------------------------------------
# SupplyChainCrossSourceValidator（编排：归一 → 收集 → 判定）
# ------------------------------------------------------------------
class SupplyChainCrossSourceValidator:
    """供应链双源校验器。

    用法::

        validator = SupplyChainCrossSourceValidator(EastMoneyProbe(), ThsAkshareProbe())
        result = validator.verify("300750", "宁德时代", board_hint="动力电池")
        # result.status in {"confirmed","partial","conflict","unverified","not_applicable"}
    """

    def __init__(
        self,
        eastmoney_probe: SupplyChainSourceProbe,
        ths_probe: SupplyChainSourceProbe,
    ) -> None:
        self._em = eastmoney_probe
        self._ths = ths_probe

    def verify(
        self,
        stock_code: Any,
        stock_name: Any,
        claim: str = "",
        board_hint: str = "",
        topic: str = "",
    ) -> VerificationResult:
        """校验单条供应链事实。永不抛异常（fail-open）。

        ``claim`` 为 LLM 语义上下文（自然语言陈述），不参与结构化判定；
        ``board_hint`` / ``topic`` 用于定位板块，``board_hint`` 优先，缺省时回退
        ``topic``，再缺省回退 ``stock_name``。
        """
        code = normalize_a_share_code(stock_code)
        if code is None:
            return _not_applicable_result(stock_code, stock_name)

        keyword = (board_hint or topic or stock_name or "").strip()
        name = str(stock_name or "")
        em = self._safe_probe(self._em, code, name, keyword)
        ths = self._safe_probe(self._ths, code, name, keyword)
        return judge_verification(code, name, em, ths, board_hint)

    @staticmethod
    def _safe_probe(
        probe: SupplyChainSourceProbe, code: str, name: str, keyword: str
    ) -> SourceEvidence:
        """逐源 fail-open：探针异常返回 available=False 证据，绝不拖垮另一源。"""
        try:
            return probe.probe(code, name, keyword)
        except Exception as exc:  # noqa: BLE001 — fail-open：源异常不影响其他源
            logger.debug(
                "[SupplyChainCrossValidate] probe %s failed: %s",
                getattr(probe, "name", "unknown"),
                exc,
            )
            return SourceEvidence(
                source=getattr(probe, "name", "unknown"),
                available=False,
                matched=False,
                error=f"{type(exc).__name__}: {exc}",
            )


# ------------------------------------------------------------------
# 默认校验器（工具层懒加载，测试可 monkeypatch）
# ------------------------------------------------------------------
_DEFAULT_VALIDATOR: Optional[SupplyChainCrossSourceValidator] = None


def get_default_validator() -> SupplyChainCrossSourceValidator:
    """惰性构建默认双源校验器（东财 + 同花顺 akshare）。

    探针构造不触发 akshare / 东财 provider 的 import（懒到 ``probe()`` 才解析），
    保证工具注册期零 IO、零重依赖。
    """
    global _DEFAULT_VALIDATOR
    if _DEFAULT_VALIDATOR is None:
        _DEFAULT_VALIDATOR = SupplyChainCrossSourceValidator(
            eastmoney_probe=EastMoneyProbe(),
            ths_probe=ThsAkshareProbe(),
        )
    return _DEFAULT_VALIDATOR
