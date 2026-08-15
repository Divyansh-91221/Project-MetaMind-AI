"""Copilot tools. Each wraps one domain capability and returns typed evidence."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import Tool, ToolResult
from app.agents.tools.glossary_tool import GlossaryTool
from app.agents.tools.governance_tool import GovernanceTool
from app.agents.tools.impact_tool import ImpactTool
from app.agents.tools.lineage_tool import LineageTool
from app.agents.tools.metadata_tool import MetadataTool
from app.agents.tools.quality_tool import QualityTool
from app.agents.tools.search_tool import SearchTool

TOOL_CLASSES: tuple[type[Tool], ...] = (
    MetadataTool,
    LineageTool,
    ImpactTool,
    SearchTool,
    GovernanceTool,
    GlossaryTool,
    QualityTool,
)


def build_toolbox(session: AsyncSession) -> dict[str, Tool]:
    """Instantiate every tool against one database session."""
    tools = [tool_cls(session) for tool_cls in TOOL_CLASSES]
    return {tool.name: tool for tool in tools}


__all__ = [
    "TOOL_CLASSES",
    "GlossaryTool",
    "GovernanceTool",
    "ImpactTool",
    "LineageTool",
    "MetadataTool",
    "QualityTool",
    "SearchTool",
    "Tool",
    "ToolResult",
    "build_toolbox",
]
