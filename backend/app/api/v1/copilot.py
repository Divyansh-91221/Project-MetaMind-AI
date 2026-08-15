"""Copilot (AI agent) endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents.agent import MetadataCopilotAgent
from app.agents.tools import build_toolbox
from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import Permission
from app.schemas.copilot import CopilotChatRequest, CopilotChatResponse

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/chat", response_model=CopilotChatResponse, summary="Ask the Copilot")
async def chat(
    payload: CopilotChatRequest, session: DbSession, principal: CurrentPrincipal
) -> CopilotChatResponse:
    """Answer a metadata question with evidence.

    The response includes the resolved entities, every piece of evidence used, and the tool
    calls that produced it, so answers are auditable rather than opaque.
    """
    principal.require(Permission.COPILOT_USE)
    agent = MetadataCopilotAgent(session)
    return await agent.chat(payload, principal=principal.subject)


@router.get("/tools", summary="List the tools available to the agent")
async def list_tools(session: DbSession, principal: CurrentPrincipal) -> list[dict[str, str]]:
    principal.require(Permission.COPILOT_USE)
    return [tool.spec() for tool in build_toolbox(session).values()]


@router.get("/examples", summary="Example questions the Copilot can answer")
async def examples(principal: CurrentPrincipal) -> list[str]:
    principal.require(Permission.COPILOT_USE)
    return [
        "What is customer_id?",
        "Where does customer_id come from?",
        "What uses customer_id?",
        "What will break if customer_id changes?",
        "Which dashboards depend on snowflake.sales?",
        "Who owns the sales dataset?",
        "Which datasets contain PII?",
        "Why is the revenue dashboard stale?",
        "What is the business definition of customer revenue?",
        "Show me the lineage of the Monthly Revenue KPI.",
    ]
