from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.client import Client

import railway
import services

mcp = FastMCP(
    name="VoxPath MCP",
    instructions=(
        "Expose VoxPath's capabilities as MCP tools: news, Indian markets, and "
        "Indian Railways lookups. This server is the single tool registry used by "
        "both the text agent and the live voice agent."
    ),
    version="0.2.0",
)


async def call_tool(name: str, arguments: dict | None = None):
    """Invoke an MCP tool by name via an in-process client. Single executor used
    by the HTTP API and the voice bridge so all tools run through this server."""
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments or {})
    if getattr(result, "is_error", False):
        raise RuntimeError(f"MCP tool '{name}' returned an error.")
    if result.structured_content is not None:
        return result.structured_content
    if result.data is not None:
        return result.data
    if result.content:
        return result.content[0].text
    return None


@mcp.resource("voxpath://health", name="health_status", description="Current service health")
def health_status() -> dict[str, str]:
    return {"status": "ok"}


@mcp.resource(
    "voxpath://capabilities",
    name="capabilities",
    description="List of capabilities currently available through the VoxPath MCP server",
)
def capabilities() -> dict[str, object]:
    return {
        "server": "VoxPath MCP",
        "tools": [
            "route_chat",
            "general_chat",
            "extract_market_tickers",
            "get_stock_price",
            "market_report",
            "list_news_sources",
            "crawl_news",
            "get_latest_headlines",
            "handle_chat",
        ],
        "resources": [
            "voxpath://health",
            "voxpath://capabilities",
            "voxpath://news/sources",
        ],
    }


@mcp.tool(description="Route a user message to the appropriate VoxPath agent")
def route_chat(message: str) -> dict[str, str]:
    return {"agent": services.route_message(message)}


@mcp.resource(
    "voxpath://news/sources",
    name="news_sources",
    description="List of configured news sources available to the VoxPath crawler",
)
def news_sources() -> dict[str, object]:
    return {"sources": services.list_news_sources()}


@mcp.tool(description="Run a general chat completion using the configured Vertex AI (Gemini) model")
def general_chat(message: str) -> dict[str, str]:
    return services.general_chat(message)


@mcp.tool(description="Extract Indian stock tickers from a user query")
def extract_market_tickers(query: str) -> dict[str, list[str]]:
    return {"tickers": services.extract_market_tickers(query)}


@mcp.tool(description="Get the latest price of ANY Indian-listed stock by company name (e.g. 'Tata Motors', 'Adani Power') or ticker (e.g. TCS, INFY), or 'NIFTY' for the index.")
def get_stock_price(ticker: str) -> dict[str, str]:
    return services.get_stock_price_smart(ticker)


@mcp.tool(description="Generate an Indian stock market report for a user query")
def market_report(query: str) -> dict[str, object]:
    return services.market_report(query)


@mcp.tool(description="List the configured news sources available to the crawler")
def list_news_sources() -> dict[str, object]:
    return {"sources": services.list_news_sources()}


@mcp.tool(description="Run the integrated news crawler across all or matching sources")
def crawl_news(source_query: str | None = None, dry_run: bool = False, limit: int | None = None) -> dict[str, object]:
    return services.crawl_news(source_query=source_query, dry_run=dry_run, limit=limit)


@mcp.tool(description="Read the latest stored headlines, optionally filtered by source or language")
def get_latest_headlines(limit: int = 10, source: str | None = None, language: str | None = None) -> dict[str, object]:
    return services.get_latest_headlines(limit=limit, source=source, language=language)


@mcp.tool(description="Handle a chat request by routing it to the correct VoxPath capability")
def handle_chat(message: str) -> dict[str, object]:
    return services.handle_chat(message)


@mcp.tool(description="Fetch the latest live Indian news headlines. Pass a region like 'Bihar' or 'Uttar Pradesh' as topic, or omit for general news.")
def get_latest_news(topic: str | None = None, limit: int = 5) -> dict[str, object]:
    return services.get_latest_news(topic=topic, limit=limit)


# --- Indian Railways (IRCTC) tools ----------------------------------------
@mcp.tool(description="Check a train ticket booking status by its 10-digit PNR number.")
def get_pnr_status(pnr: str) -> dict[str, object]:
    return railway.get_pnr_status(pnr)


@mcp.tool(description="Look up the IRCTC station code(s) for a city or station name (e.g. 'Delhi' -> 'NDLS').")
def resolve_station_code(station_name: str) -> dict[str, object]:
    return railway.resolve_station_code(station_name)


@mcp.tool(description="Get the live running status of a train: current location, delay, running status. Date optional (DD-MM-YYYY).")
def get_live_train_status(train_number: str, date: str | None = None) -> dict[str, object]:
    return railway.get_live_train_status(train_number, date)


@mcp.tool(description="Get a train's full route and timetable with all stops and timings.")
def get_train_schedule(train_number: str) -> dict[str, object]:
    return railway.get_train_schedule(train_number)


@mcp.tool(description="Find all trains between two stations or cities (accepts station codes or city names). Date optional (DD-MM-YYYY).")
def search_trains(source: str, destination: str, date: str | None = None) -> dict[str, object]:
    return railway.search_trains(source, destination, date)


@mcp.tool(description="Check class-wise seat availability between two station codes on a date (DD-MM-YYYY).")
def check_seat_availability(source: str, destination: str, date: str, train_number: str | None = None) -> dict[str, object]:
    return railway.check_seat_availability(source, destination, date, train_number)


@mcp.tool(description="Get class-wise ticket fares for a train between two station codes. Date optional (DD-MM-YYYY).")
def get_fare(train_number: str, source: str, destination: str, date: str | None = None) -> dict[str, object]:
    return railway.get_fare(train_number, source, destination, date)
