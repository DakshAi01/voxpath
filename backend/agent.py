"""LangGraph "root node" text agent for VoxPath.

A single ReAct-style agent that routes any text request to the
right tool by intent. Its tools are loaded from the MCP server — the same single
registry the voice agent uses — so there is one tool layer behind both surfaces.
"""

from __future__ import annotations

import inspect
import os

from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import trim_messages
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

import memory
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
    "stations, date) is missing, ask for it. Keep answers short and clear. "
    "You have long-term memory across conversations: call search_memories "
    "before answering anything that depends on who the user is or what they "
    "prefer, and when they refer to something they told you earlier. Call "
    "save_memory when the user states a durable fact about themselves (a "
    "name, a preference, a home station, a standing interest) -- never for "
    "the answer to the current question, and never for live data."
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
    "save_memory",
    "search_memories",
]

_agent = None
_saver = None
_store = None

# Every turn replays the whole thread, and the railway and news tools return
# bulky JSON, so an unbounded history would hit the context limit (and the bill)
# within a few dozen turns. The full history still lives in the checkpointer --
# only the model's view of it is trimmed.
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "3000"))

# All chat turns share one thread until the API grows a session concept; with a
# checkpointer attached LangGraph requires a thread_id on every invocation.
DEFAULT_THREAD_ID = "voxpath-default"


async def init_agent(saver=None, store=None) -> None:
    """Build the single app-lifetime agent. Called once from the lifespan.

    Built at startup rather than on the first request so that the checkpointer
    and store (which do not exist until the pool is open) are always attached,
    and so a bad API key or a missing MCP tool fails the boot instead of some
    user's chat message. saver/store are None when DATABASE_URL is unset, which
    yields a working agent with no conversation memory.
    """
    global _saver, _store, _agent
    _saver = saver
    _store = store
    _agent = await _build_agent()


def _build_pre_model_hook(llm):
    """Trim the thread to a token budget before each model call.

    Returns `llm_input_messages`, which feeds the LLM without rewriting the
    stored messages, so nothing is lost from the checkpointer. start_on="human"
    matters: dropping an AI tool-call while keeping its ToolMessage leaves an
    orphan that OpenAI rejects outright.
    """

    def trim(state):
        trimmed = trim_messages(
            state["messages"],
            max_tokens=MAX_HISTORY_TOKENS,
            token_counter=llm,
            strategy="last",
            start_on="human",
            end_on=("human", "tool"),
            include_system=True,
            allow_partial=False,
        )
        # trim_messages can return nothing if a single message blows the budget;
        # sending an empty list would error, so fall back to the latest turn.
        if not trimmed:
            trimmed = state["messages"][-1:]
        return {"llm_input_messages": trimmed}

    return trim


async def _build_agent():
    # FastMCP 3.x: get_tools() (dict) was replaced by list_tools() (list).
    tools_map = {tool.name: tool for tool in await mcp.list_tools()}
    lc_tools = []
    for name in AGENT_TOOLS:
        tool = tools_map.get(name)
        if tool is None:
            log.warning("agent tool %s not found in MCP registry", name)
            continue
        # from_function() puts whatever it is given in the sync `func` slot, so
        # an async tool would be called without being awaited -- it returns a
        # coroutine and the body never runs. Async tools must go to `coroutine`.
        if inspect.iscoroutinefunction(tool.fn):
            lc_tool = StructuredTool.from_function(
                coroutine=tool.fn, name=name, description=tool.description
            )
        else:
            lc_tool = StructuredTool.from_function(
                tool.fn, name=name, description=tool.description
            )
        lc_tools.append(lc_tool)
    llm = services.build_llm()
    log.info("LangGraph agent built with %d MCP tools", len(lc_tools))
    return create_react_agent(
        llm,
        lc_tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=_saver,
        store=_store,
        pre_model_hook=_build_pre_model_hook(llm),
    )


async def agent_chat(
    message: str, thread_id: str | None = None, user_id: str | None = None
) -> str:
    """Run one text turn through the LangGraph agent; return the reply text.

    thread_id scopes short-term memory (one conversation); user_id scopes
    long-term memory (every conversation that person has had). There is no auth
    yet so user_id is normally unset, but the memory tools read it from this
    config, so wiring real users later needs no change here.
    """
    if _agent is None:
        raise RuntimeError(
            "agent not initialised - init_agent() must run in the app lifespan"
        )
    config = {
        "configurable": {
            "thread_id": thread_id or DEFAULT_THREAD_ID,
            "user_id": user_id or memory.DEFAULT_USER_ID,
        }
    }
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=message)]}, config=config
    )
    final = result["messages"][-1]
    content = final.content
    return content if isinstance(content, str) else str(content)
