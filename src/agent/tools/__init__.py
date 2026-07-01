# -*- coding: utf-8 -*-
"""
Agent tools package.

Provides ToolRegistry, @tool decorator, and wrapped tools
for the stock analysis agent.
"""

from src.agent.tools.registry import ToolRegistry, ToolDefinition, ToolParameter, tool
from src.agent.tools.knowledge_base_tools import (
    SEARCH_KNOWLEDGE_BASE_TOOL,
    LIST_KNOWLEDGE_DOCUMENTS_TOOL,
    _handle_search_knowledge_base,
    _handle_list_knowledge_documents,
)

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ToolParameter",
    "tool",
    "SEARCH_KNOWLEDGE_BASE_TOOL",
    "LIST_KNOWLEDGE_DOCUMENTS_TOOL",
    "_handle_search_knowledge_base",
    "_handle_list_knowledge_documents",
]
