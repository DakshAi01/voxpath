"""LangGraph "root node" text agent for VoxPath.

A single ReAct-style agent (ChatVertexAI) that routes any text request to the
right tool by intent. Its tools are loaded from the MCP server — the same single
registry the voice agent uses — so there is one tool layer behind both surfaces.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

import services
from logging_config import get_logger
from mcp_server import mcp

log = get_logger("voxpath.agent")

SYSTEM_PROMPT = (
    "You are VoxPath, a concise, friendly Indian assistant. "
    "Use the available tools for anything about live news, Indian stock/market "
    "prices, or Indian Railways (PNR status, train running status, schedules, "
    "train search, seat availability, fares). "
    "Your training data is out of date, so NEVER answer those from memory — call "
    "the matching tool and answer from its result. For railway fares/availability "
    "you need IRCTC station codes like NDLS or HJP; if the user gives a city name, "
    "call resolve_station_code first. If a required detail (PNR, train number, "
    "stations, date) is missing, ask for it. Keep answers short and clear."
)

# Tools (by MCP name) the text agent is allowed to call.
AGENT_TOOLS = [
    "get_latest_news",
    "get_stock_price",
    "get_pnr_status",
    "resolve_station_code",
    "get_live_train_status",
    "get_train_schedule",
    "search_trains",
    "check_seat_availability",
    "get_fare",
]

_agent = None


async def _build_agent():
    # FastMCP 3.x: get_tools() (dict) was replaced by list_tools() (list).
    tools_map = {tool.name: tool for tool in await mcp.list_tools()}
    lc_tools = []
    for name in AGENT_TOOLS:
        tool = tools_map.get(name)
        if tool is None:
            log.warning("agent tool %s not found in MCP registry", name)
            continue
        lc_tools.append(
            StructuredTool.from_function(tool.fn, name=name, description=tool.description)
        )
    llm = services.build_llm()
    log.info("LangGraph agent built with %d MCP tools", len(lc_tools))
    return create_react_agent(llm, lc_tools, prompt=SYSTEM_PROMPT)


async def agent_chat(message: str) -> str:
    """Run one text turn through the LangGraph agent; return the reply text."""
    global _agent
    if _agent is None:
        _agent = await _build_agent()
    result = await _agent.ainvoke({"messages": [HumanMessage(content=message)]})
    final = result["messages"][-1]
    content = final.content
    return content if isinstance(content, str) else str(content)
