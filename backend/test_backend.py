import asyncio

from fastapi.testclient import TestClient

import main
import mcp_server
import news_crawler
import services


def test_route_message_routes_market_queries():
    assert services.route_message("What is the stock price of TCS today?") == "market_agent"


def test_route_message_routes_news_queries():
    assert services.route_message("crawl latest news headlines") == "news_agent"


def test_route_message_routes_general_queries():
    assert services.route_message("Hello there") == "general_agent"


def test_market_report_uses_extracted_tickers(monkeypatch):
    class FakeLLM:
        def invoke(self, prompt: str):
            assert "INFY" in prompt
            return type("Resp", (), {"content": "TCS, NIFTY"})()

    monkeypatch.setattr(services, "build_llm", lambda: FakeLLM())
    monkeypatch.setattr(services, "get_stock_price", lambda ticker: f"{ticker} mock-price")

    result = services.market_report("Give me TCS and market prices", llm=services.build_llm())

    assert result["report"] == "TCS mock-price\n^NSEI mock-price"
    assert "Indian Stock Market Update" in result["text"]


def test_general_chat_returns_model_response(monkeypatch):
    class FakeLLM:
        def invoke(self, prompt: str):
            assert prompt == "Hello!"
            return type("Resp", (), {"content": "Hi there"})()

    monkeypatch.setattr(services, "build_llm", lambda: FakeLLM())

    result = services.general_chat("Hello!", llm=services.build_llm())

    assert result["text"] == "Hi there"


def test_parse_rss_success():
    sample_rss = b"""<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0"><channel><item>
      <title>Test RSS Headline for Parser</title>
      <link>https://example.com/art1</link>
      <pubDate>Thu, 26 Mar 2026 00:00:00 +0000</pubDate>
    </item></channel></rss>"""
    config = {"name": "Test RSS", "url": "https://example.com", "max_items": 5, "language": "en"}

    results = news_crawler.parse_rss(sample_rss, config)

    assert len(results) == 1
    assert results[0]["headline"] == "Test RSS Headline for Parser"
    assert results[0]["link"] == "https://example.com/art1"


def test_parse_html_fallback():
    sample_html = b'<html><body><div><h2>Headline that is long enough for the parser</h2><a href="/art">Link</a></div></body></html>'
    config = {
        "name": "Test HTML Fallback",
        "url": "https://example.com",
        "selector": ".non-existent",
        "max_items": 5,
        "language": "en",
    }

    results, fallback = news_crawler.parse_html(sample_html, config, "utf-8")

    assert fallback is True
    assert len(results) == 1
    assert results[0]["headline"] == "Headline that is long enough for the parser"
    assert results[0]["link"] == "https://example.com/art"


def test_news_chat_uses_latest_headlines(monkeypatch):
    monkeypatch.setattr(
        services,
        "get_latest_headlines",
        lambda limit=5, source=None, language=None: {
            "status": "ok",
            "count": 1,
            "headlines": [{"headline": "RBI policy update", "source": "The Hindu", "language": "en"}],
        },
    )

    result = services.news_chat("latest news headlines")

    assert result["agent"] == "news_agent"
    assert result["text"].startswith("Latest headlines:\n\n- ")
    assert "RBI policy update" in result["text"]


def test_news_chat_uses_requested_headline_count(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_latest_headlines(limit=5, source=None, language=None):
        captured["limit"] = limit
        return {
            "status": "ok",
            "count": 2,
            "headlines": [
                {"headline": "Headline 1", "source": "Source A", "language": "en"},
                {"headline": "Headline 2", "source": "Source B", "language": "en"},
            ],
        }

    monkeypatch.setattr(services, "get_latest_headlines", fake_get_latest_headlines)

    result = services.news_chat("give me top 10 news headlines from India")

    assert captured["limit"] == 10
    assert "Headline 1" in result["text"]
    assert "Headline 2" in result["text"]


def test_list_news_sources_includes_requested_newspapers():
    source_names = {source["name"] for source in services.list_news_sources()}

    assert "Times of India" in source_names
    assert "The Hindu" in source_names


def test_list_news_sources_includes_bihar_sources():
    source_names = {source["name"] for source in services.list_news_sources()}

    assert "Times of India Patna" in source_names
    assert "Amar Ujala Bihar" in source_names
    assert "Live Hindustan Bihar" in source_names
    assert "Dainik Jagran Bihar" in source_names


def test_list_news_sources_includes_uttar_pradesh_sources():
    source_names = {source["name"] for source in services.list_news_sources()}

    assert "Times of India Uttar Pradesh (Lucknow)" in source_names
    assert "Amar Ujala Uttar Pradesh" in source_names
    assert "Live Hindustan Uttar Pradesh" in source_names
    assert "Dainik Jagran Uttar Pradesh" in source_names


def test_detect_news_source_query_maps_uttar_pradesh_aliases():
    assert services.detect_news_source_query("latest Uttar Pradesh election news") == "Uttar Pradesh"
    assert services.detect_news_source_query("show me यूपी headlines") == "Uttar Pradesh"


def test_mcp_capabilities_include_news_tools():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    resources = asyncio.run(mcp_server.mcp.list_resources())
    
    tool_names = {t.name for t in tools}
    resource_uris = {str(r.uri) for r in resources}

    assert "crawl_news" in tool_names
    assert "get_latest_headlines" in tool_names
    assert "voxpath://news/sources" in resource_uris


def test_chat_endpoint_uses_langgraph_agent(monkeypatch):
    import agent

    async def fake_agent_chat(message: str) -> str:
        assert message == "Hello!"
        return "Agent says hello"

    monkeypatch.setattr(agent, "agent_chat", fake_agent_chat)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "Hello!"})

    assert response.status_code == 200
    assert response.json() == {"text": "Agent says hello", "audio": None}
