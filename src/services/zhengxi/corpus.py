# -*- coding: utf-8 -*-
"""郑希语料加载与关键词检索。

移植自 zhengxi-views/scripts/search_corpus.py，改为函数库：
段落级 AND/OR 关键词匹配，每条命中带结构化出处（类型/日期/标题/来源/链接），
供 Agent 工具返回给 LLM 做可溯源引用。
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, List, Optional

from src.services.zhengxi.paths import corpus_dir, corpus_index_path

# 语料按这三个类型分子目录存放
DOC_TYPES = ("定期报告", "基金经理手记", "媒体报道")


def load_doc(path: str) -> dict[str, Any]:
    """解析一篇语料 markdown。

    语料格式::

        # 标题
        - 日期：YYYY-MM-DD
        - 原文链接：<url>
        - 来源：<可选>
        ---
        正文（段落以空行分隔）
    """
    text = open(path, encoding="utf-8").read()
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    date_match = re.search(r"日期[:：]\s*([0-9\-]+)", text)
    src_match = re.search(r"来源[:：]\s*(.+)", text)
    link_match = re.search(r"原文链接[:：]\s*(\S+)", text)
    body = text.split("---", 1)[-1] if "---" in text else text
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    return {
        "title": title_match.group(1).strip() if title_match else "",
        "date": date_match.group(1).strip() if date_match else "",
        "source": src_match.group(1).strip() if src_match else "",
        "link": link_match.group(1).strip() if link_match else "",
        "paras": paras,
    }


def search_corpus(
    keywords: List[str],
    *,
    match_all: bool = True,
    doc_types: Optional[List[str]] = None,
    context: int = 0,
    max_results: int = 20,
) -> List[dict[str, Any]]:
    """在郑希语料中按关键词检索段落。

    Args:
        keywords: 关键词列表。
        match_all: ``True`` = AND（段落须命中全部关键词）；
            ``False`` = OR（命中任一即可）。
        doc_types: 限定文档类型（``定期报告``/``基金经理手记``/``媒体报道``）。
        context: 命中段落附带前后各 N 段，便于看上下文。
        max_results: 最多返回片段数。

    Returns:
        命中片段列表，每项含 ``date/type/title/source/link/path/matched/snippet``，
        按日期降序（新 → 旧）。
    """
    if not keywords:
        return []
    types = doc_types or list(DOC_TYPES)
    # 关键词按主题扩展为同义词组（组内 OR、组间 AND），降低用词差异导致的召回盲区
    from src.services.zhengxi.synonyms import expand_keywords

    groups = expand_keywords(keywords)
    hits: List[dict[str, Any]] = []
    for doc_type in types:
        for path in sorted(glob.glob(os.path.join(corpus_dir(), doc_type, "*.md"))):
            doc = load_doc(path)
            rel = os.path.relpath(path, corpus_dir())
            for idx, para in enumerate(doc["paras"]):
                hit_groups = [g for g in groups if any(syn in para for syn in g)]
                ok = (len(hit_groups) == len(groups)) if match_all else (len(hit_groups) > 0)
                if not ok:
                    continue
                # matched 记录命中的原始关键词（供显示），组内具体命中的词也一并带上
                matched = [
                    k for k, g in zip(keywords, groups)
                    if any(syn in para for syn in g)
                ]
                lo = max(0, idx - context)
                hi = min(len(doc["paras"]), idx + context + 1)
                hits.append({
                    "date": doc["date"],
                    "type": doc_type,
                    "title": doc["title"],
                    "source": doc["source"],
                    "link": doc["link"],
                    "path": rel,
                    "matched": matched,
                    "snippet": "\n".join(doc["paras"][lo:hi]),
                })
    hits.sort(key=lambda h: h["date"], reverse=True)
    return hits[:max_results]


def load_corpus_summary() -> dict[str, Any]:
    """语料库概览（类型计数 + 日期范围），用于向 LLM 介绍可用语料规模。"""
    idx_path = corpus_index_path()
    if os.path.exists(idx_path):
        try:
            idx = json.load(open(idx_path, encoding="utf-8"))
            return {
                "manager": idx.get("manager", "郑希"),
                "counts": idx.get("counts", {}),
                "date_range": idx.get("date_range", {}),
            }
        except Exception:
            pass
    counts = {
        doc_type: len(glob.glob(os.path.join(corpus_dir(), doc_type, "*.md")))
        for doc_type in DOC_TYPES
    }
    return {"manager": "郑希", "counts": counts, "date_range": {}}
