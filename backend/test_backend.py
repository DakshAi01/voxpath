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
    import auth

    user = auth.User(id="u1", email="a@example.com")

    async def fake_agent_chat(message: str, thread_id: str | None = None, user_id: str | None = None) -> str:
        assert message == "Hello!"
        assert user_id == "u1"
        return "Agent says hello"

    async def fake_claim_thread(thread_id, owner):
        assert owner == user

    monkeypatch.setattr(agent, "agent_chat", fake_agent_chat)
    monkeypatch.setattr(auth, "claim_thread", fake_claim_thread)
    main.app.dependency_overrides[auth.current_user] = lambda: user
    try:
        client = TestClient(main.app)
        response = client.post("/chat", json={"message": "Hello!"})
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"text": "Agent says hello", "audio": None}


def test_chat_endpoint_requires_a_token():
    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "Hello!"})
    assert response.status_code == 401


def _guarded_echo():
    import auth

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    from starlette.applications import Starlette

    app = Starlette()
    app.mount("/mcp", auth.require_token(inner))
    return TestClient(app)


def test_mcp_mount_rejects_missing_and_forged_tokens(monkeypatch):
    import auth

    monkeypatch.setattr(auth, "JWT_SECRET", "test-secret-" + "x" * 32)
    client = _guarded_echo()
    assert client.post("/mcp/").status_code == 401
    assert client.post("/mcp/", headers={"Authorization": "Bearer nonsense"}).status_code == 401

    forged = auth.jwt.encode({"sub": "u1", "email": "a@example.com"}, "wrong-key-" + "y" * 32, algorithm="HS256")
    assert client.post("/mcp/", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_mcp_mount_accepts_a_valid_token(monkeypatch):
    import auth

    monkeypatch.setattr(auth, "JWT_SECRET", "test-secret-" + "x" * 32)
    token = auth.create_token(auth.User(id="u1", email="a@example.com"))
    client = _guarded_echo()
    response = client.post("/mcp/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_real_mcp_mount_is_guarded():
    client = TestClient(main.app)
    assert client.post("/mcp/", json={}).status_code == 401


def _rail_client(handler):
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_search_trains_queries_every_pair_concurrently(monkeypatch):
    import railway

    monkeypatch.setenv("RAPIDAPI_KEY", "k")
    in_flight = peak = 0

    async def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        src = request.url.params["source"]
        # Every pair returns the shared train 12951; only NDLS adds its own.
        data = [{"trainNumber": "12951", "departure": "16:55", "from": {"code": src}}]
        if src == "NDLS":
            data.append({"trainNumber": "22210", "departure": "23:00", "from": {"code": src}})
        return railway.httpx.Response(200, json={"data": data})

    async def run():
        async with _rail_client(handler) as client:
            return await railway.search_trains("delhi", "mumbai", "10-10-2026", client=client)

    result = asyncio.run(run())

    assert result["train_count"] == 2
    assert [t["train_number"] for t in result["trains"]] == ["12951", "22210"]
    # De-duplication keeps the first pair in order, not whichever finished first.
    assert result["trains"][0]["source_station"].endswith("(NDLS)")
    assert 1 < peak <= railway.SEARCH_CONCURRENCY


def test_search_trains_returns_partial_results_at_the_deadline(monkeypatch):
    import railway

    monkeypatch.setenv("RAPIDAPI_KEY", "k")
    monkeypatch.setattr(railway, "SEARCH_DEADLINE", 0.2)

    async def handler(request):
        if request.url.params["source"] != "NDLS":
            await asyncio.sleep(5)
        return railway.httpx.Response(200, json={"data": [{"trainNumber": "1", "departure": "01:00"}]})

    async def run():
        async with _rail_client(handler) as client:
            return await railway.search_trains("delhi", "CSMT", "10-10-2026", client=client)

    result = asyncio.run(run())
    assert result["train_count"] == 1


def test_search_trains_survives_failing_pairs_and_missing_key(monkeypatch):
    import railway

    async def handler(request):
        if request.url.params["source"] == "NDLS":
            raise railway.httpx.ConnectError("boom")
        return railway.httpx.Response(500)

    async def run():
        async with _rail_client(handler) as client:
            return await railway.search_trains("delhi", "CSMT", "10-10-2026", client=client)

    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    assert "RAPIDAPI_KEY" in asyncio.run(run())["error"]

    monkeypatch.setenv("RAPIDAPI_KEY", "k")
    assert asyncio.run(run()) == {"error": "No trains found from DELHI to CSMT"}
