import os
import re
from typing import Any

import yfinance as yf
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

import news_crawler
import stock_resolver
from logging_config import get_logger

load_dotenv()

log = get_logger("voxpath.services")


def build_llm() -> BaseChatModel:
    """Build the chat model used by the text agent.

    Uses OpenAI, authenticated with OPENAI_API_KEY from the environment. The
    model is set by OPENAI_MODEL. (The voice, image and video surfaces still
    use Vertex AI / Veo directly and are unaffected by this.)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to backend/.env to use the chat agent."
        )
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        temperature=0,
        max_retries=0,
    )


def get_market_keywords() -> list[str]:
    return ["stock price", "stock market", "price of", "nifty", "sensex", "shares of", "ticker"]


def get_news_keywords() -> list[str]:
    return ["news", "headline", "headlines", "crawl", "crawler", "newspaper", "rss", "bulletin"]


def route_message(message: str) -> str:
    lowered = message.lower()
    # Prioritize news keywords if 'share' (as in sharing news) might be used
    if any(keyword in lowered for keyword in get_news_keywords()):
        return "news_agent"
    if any(keyword in lowered for keyword in get_market_keywords()) or "share" in lowered:
        # If it contains share but NOT news (handled above), it might be market
        # but let's be even more careful.
        # If it has "share" but none of the specific market keywords, 
        # only route to market if it looks like a ticker query or price query.
        if "share" in lowered and not any(k in lowered for k in ["price", "stock", "market"]):
             # "share the news" -> should have been caught by news_agent check
             # "share today's update" -> might fall through to general
             pass
        else:
             return "market_agent"

    if any(keyword in lowered for keyword in get_market_keywords()):
        return "market_agent"

    return "general_agent"


def normalize_ticker(ticker: str) -> str:
    if ticker.endswith(".NS") or ticker.endswith(".BO") or ticker.startswith("^"):
        return ticker
    return f"{ticker.upper()}.NS"


def _price_for_symbol(symbol: str) -> float | None:
    """Best-effort live/last price for a fully-qualified Yahoo symbol."""
    try:
        ticker = yf.Ticker(symbol)
        try:
            price = ticker.fast_info.last_price
            if price is not None:
                return float(price)
        except Exception:  # noqa: BLE001 - fall back to history below
            pass
        history = ticker.history(period="5d")
        if not history.empty:
            return float(history["Close"].iloc[-1])
    except Exception as error:  # noqa: BLE001
        log.debug("price lookup failed for %s: %s", symbol, error)
    return None


def _candidate_symbols(query: str) -> list[str]:
    """Resolve a company name or ticker to ordered Yahoo symbol candidates.

    Uses Yahoo search so any listed company works (and so ticker changes like
    TATAMOTORS -> TMCV/TMPV resolve to the current symbol), preferring NSE then BSE.
    """
    q = query.strip()
    candidates: list[str] = []
    if q.endswith((".NS", ".BO")) or q.startswith("^"):
        candidates.append(q)

    # 1) Official NSE listing (covers every NSE-listed company by name/symbol).
    candidates += [f"{sym}.NS" for sym in stock_resolver.nse_matches(q)]

    # 2) Yahoo search (catches renames/demergers and BSE-only names).
    try:
        quotes = yf.Search(q).quotes
        candidates += [r["symbol"] for r in quotes if r.get("symbol", "").endswith(".NS")]
        candidates += [r["symbol"] for r in quotes if r.get("symbol", "").endswith(".BO")]
    except Exception as error:  # noqa: BLE001
        log.debug("symbol search failed for %r: %s", q, error)

    token = q.upper().replace(" ", "")
    if token and not any(c.endswith((".NS", ".BO")) for c in candidates):
        candidates += [f"{token}.NS", f"{token}.BO"]

    seen: set[str] = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def get_stock_price(query: str) -> str:
    """Live price for any Indian-listed stock by company name OR ticker."""
    if not query or not query.strip():
        return "Please specify a stock or company name."
    q = query.strip()
    if q.upper() in ("NIFTY", "NIFTY50", "NIFTY 50"):
        q = "^NSEI"

    for symbol in _candidate_symbols(q):
        price = _price_for_symbol(symbol)
        if price is not None:
            log.info("stock %r -> %s = %.2f", query, symbol, price)
            return f"{symbol}: {price:.2f} INR"

    log.warning("no price found for %r", query)
    return f"Could not find live price data for '{query}'."


def extract_market_tickers(query: str, llm: BaseChatModel | None = None) -> list[str]:
    llm = llm or build_llm()
    extract_prompt = (
        f"Extract Indian stock tickers from this query: '{query}'. Return only a comma-separated "
        "list of symbols (e.g. TCS, INFY, RELIANCE). Use 'INFY' for Infosys. If none, return 'NIFTY'."
    )
    log.debug("extracting tickers via LLM for: %r", query[:80])
    llm_response = llm.invoke(extract_prompt)
    ticker_text = str(llm_response.content).strip()
    tickers = [ticker.strip() for ticker in ticker_text.split(",") if ticker.strip()]
    log.info("extracted tickers: %s", tickers)
    return tickers


def market_report(query: str, llm: BaseChatModel | None = None) -> dict[str, Any]:
    tickers = extract_market_tickers(query, llm=llm)
    results = [get_stock_price(ticker if ticker != "NIFTY" else "^NSEI") for ticker in tickers]
    report = "\n".join(results)
    return {
        "agent": "market_agent",
        "tickers": tickers,
        "report": report,
        "text": f"Indian Stock Market Update\n\n{report}",
    }


def general_chat(message: str, llm: BaseChatModel | None = None) -> dict[str, str]:
    llm = llm or build_llm()
    log.debug("general chat LLM invoke: %r", message[:80])
    response = llm.invoke(message)
    return {
        "agent": "general_agent",
        "text": str(response.content),
    }


def handle_chat(message: str, llm: BaseChatModel | None = None) -> dict[str, Any]:
    selected_agent = route_message(message)
    log.info("routed to %s: %r", selected_agent, message[:80])
    if selected_agent == "market_agent":
        return market_report(message, llm=llm)
    if selected_agent == "news_agent":
        return news_chat(message)
    return general_chat(message, llm=llm)


def list_news_sources() -> list[dict]:
    return news_crawler.list_news_sources()


def crawl_news(source_query: str | None = None, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    return news_crawler.crawl_news(source_query=source_query, dry_run=dry_run, limit=limit)


def get_latest_headlines(limit: int = 10, source: str | None = None, language: str | None = None) -> dict[str, Any]:
    return news_crawler.get_latest_headlines(limit=limit, source=source, language=language)


def get_latest_news(topic: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Curated latest news for agents: stored headlines, with a general fallback
    if a free-text topic matches no source, and a one-off crawl if storage is empty."""
    topic = (topic or "").strip() or None

    def read(src: str | None) -> list[dict]:
        return get_latest_headlines(limit=limit, source=src).get("headlines") or []

    headlines = read(topic)
    if not headlines and topic:
        log.info("news topic=%r matched nothing, falling back to general", topic)
        headlines = read(None)
    if not headlines:
        try:
            headlines = crawl_news(source_query=None, limit=limit).get("headlines") or []
        except Exception as error:  # noqa: BLE001
            log.warning("news fallback crawl failed: %s", error)
    items = [{"headline": h["headline"], "source": h["source"]} for h in headlines[:limit]]
    return {"headlines": items, "count": len(items)}


def get_stock_price_smart(ticker: str) -> dict[str, str]:
    """Stock price by company name or ticker (handles the NIFTY index alias)."""
    return {"result": get_stock_price(ticker or "NIFTY")}


def detect_news_source_query(message: str) -> str | None:
    lowered = message.lower()
    alias_map = {
        "bihar": "Bihar",
        "uttar pradesh": "Uttar Pradesh",
        "uttar-pradesh": "Uttar Pradesh",
        "up news": "Uttar Pradesh",
        "up election": "Uttar Pradesh",
        "यूपी": "Uttar Pradesh",
        "उत्तर प्रदेश": "Uttar Pradesh",
    }
    for alias, canonical in alias_map.items():
        if alias in lowered:
            return canonical
    for source in news_crawler.list_news_sources():
        if source["name"].lower() in lowered:
            return source["name"]
    return None


def detect_news_language(message: str) -> str | None:
    lowered = message.lower()
    if "hindi" in lowered:
        return "hi"
    if "english" in lowered:
        return "en"
    return None


def detect_requested_headline_limit(message: str, default: int = 5, maximum: int = 25) -> int:
    match = re.search(r"\b(?:top|latest|give me|show me|get me)?\s*(\d{1,2})\b", message.lower())
    if not match:
        return default
    return max(1, min(int(match.group(1)), maximum))


def format_headline_list(items: list[dict], title: str = "Latest headlines:") -> str:
    lines = [title, ""]
    lines.extend(f"- {item['headline']} ({item['source']})" for item in items)
    return "\n".join(lines)


def news_chat(message: str) -> dict[str, Any]:
    lowered = message.lower()
    source_query = detect_news_source_query(message)
    language = detect_news_language(message)
    limit = detect_requested_headline_limit(message)

    if "crawl" in lowered or "fetch" in lowered or "run" in lowered:
        result = crawl_news(source_query=source_query, dry_run=False, limit=limit)
        if result["status"] == "no_match":
            return {"agent": "news_agent", "text": result["message"], "data": result}

        summary_lines = [
            f"News crawl complete. Saved {result['saved']} new headlines from {len(result['summary'])} sources.",
        ]
        if source_query:
            summary_lines.append(f"Filtered source: {source_query}")
        if result["headlines"]:
            summary_lines.append("")
            summary_lines.append(format_headline_list(result["headlines"][:limit], title="Top saved headlines:"))
        return {
            "agent": "news_agent",
            "text": "\n".join(summary_lines),
            "data": result,
        }

    latest = get_latest_headlines(limit=limit, source=source_query, language=language)
    if latest["count"] == 0:
        guidance = "No stored headlines found yet. Ask me to crawl the news first."
        if source_query:
            guidance = f"No stored headlines found for {source_query}. Ask me to crawl that source first."
        return {"agent": "news_agent", "text": guidance, "data": latest}

    return {
        "agent": "news_agent",
        "text": format_headline_list(latest["headlines"]),
        "data": latest,
    }


def build_fallback_text(user_text: str | None) -> str:
    received_text = user_text.strip() if user_text else ""
    if received_text:
        return (
            "I received your message, but the live AI service is currently unavailable due to API quota limits. "
            f"Your message was: '{received_text}'. Please try again later or switch to a key with active quota."
        )
    return (
        "I could not reach the live AI service because the API quota is exhausted. "
        "Please try again later or switch to a key with active quota."
    )
