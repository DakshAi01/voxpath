import services

def test_route_message_routes_market_queries():
    assert services.route_message("What is the stock price of TCS today?") == "market_agent"


def test_route_message_routes_news_queries():
    assert services.route_message("crawl latest news headlines") == "news_agent"


def test_route_message_routes_general_queries():
    assert services.route_message("Hello there") == "general_agent"


def test_route_message_misroutes_share_news():
    # This was the reproduction test for the 'share' keyword bug
    assert services.route_message("share today's news") == "news_agent"


def test_normalize_ticker():
    assert services.normalize_ticker("TCS") == "TCS.NS"
    assert services.normalize_ticker("RELIANCE.NS") == "RELIANCE.NS"
    assert services.normalize_ticker("^NSEI") == "^NSEI"


def test_detect_requested_headline_limit():
    assert services.detect_requested_headline_limit("give me 10 headlines") == 10
    assert services.detect_requested_headline_limit("show me latest news") == 5
    assert services.detect_requested_headline_limit("top 50 news", maximum=25) == 25
