from __future__ import annotations

import hashlib
import random
import re
import string
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException
from urllib3.util.retry import Retry

import news_storage
from news_config import MAX_WORKERS, SIMILARITY_THRESHOLD, SOURCES, TIMEOUT, USER_AGENTS

domain_locks: dict[str, Lock] = {}
last_request_time: dict[str, float] = {}
state_lock = Lock()


def _first_node(parent, *tags):
    for tag in tags:
        node = parent.find(tag)
        if node is not None:
            return node
    return None


def get_domain_lock(url: str) -> tuple[Lock, str]:
    domain = urlparse(url).netloc
    with state_lock:
        if domain not in domain_locks:
            domain_locks[domain] = Lock()
            last_request_time[domain] = 0
        return domain_locks[domain], domain


def fetch_url_with_rate_limit(url: str) -> tuple[bytes, str | None]:
    lock, domain = get_domain_lock(url)
    with lock:
        elapsed = time.time() - last_request_time[domain]
        delay = random.uniform(1.0, 2.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)

        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))

        headers = {"User-Agent": random.choice(USER_AGENTS)}
        response = session.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        if response.encoding == "ISO-8859-1":
            response.encoding = response.apparent_encoding

        last_request_time[domain] = time.time()
        return response.content, response.encoding


def clean_mojibake(text: str) -> str:
    if not text:
        return ""
    try:
        # Common fix for UTF-8 read as CP1252/ISO-8859-1
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Already correct or unfixable via this method
        return text


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = clean_mojibake(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = " ".join(text.split())
    return text.strip()


def get_similarity(text_a: str, text_b: str) -> float:
    def get_tokens(text: str) -> set[str]:
        if not text:
            return set()
        table = str.maketrans("", "", string.punctuation)
        return set(text.lower().translate(table).split())

    set_a = get_tokens(text_a)
    set_b = get_tokens(text_b)
    if not set_a or not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)


def generate_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_valid_headline(headline: str, link: str, source_url: str) -> bool:
    if not headline or len(headline) < 15:
        return False
    if link.rstrip("/") == source_url.rstrip("/"):
        return False

    noise = [
        "read more",
        "click here",
        "subscribe",
        "latest updates",
        "home",
        "privacy policy",
        "contact us",
        "about us",
        "follow us",
        "breaking news",
        "live updates",
    ]
    lowered = headline.lower()
    if any(entry in lowered for entry in noise):
        return False
    if any(lowered.startswith(label + ":") for label in ["video", "audio", "gallery"]):
        return False
    if len(headline.split()) < 3:
        return False
    return True


def parse_rss(content: bytes, source_config: dict) -> list[dict]:
    results: list[dict] = []
    max_items = source_config.get("max_items", 10)
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return results

    items = root.findall(".//item") or root.findall(".//{*}entry")
    for item in items[:max_items]:
        title_node = _first_node(item, "title", "{*}title")
        link_node = _first_node(item, "link", "{*}link")
        pub_node = _first_node(item, "pubDate", "{*}pubDate", "published", "{*}published", "updated", "{*}updated")

        headline = normalize_text(title_node.text if title_node is not None and title_node.text else "")
        link = ""
        if link_node is not None:
            link = link_node.text if link_node.text else link_node.attrib.get("href", "")
        published = pub_node.text if pub_node is not None and pub_node.text else datetime.now(timezone.utc).isoformat()

        if is_valid_headline(headline, link, source_config["url"]):
            results.append(
                {
                    "headline": headline,
                    "link": link,
                    "source": source_config["name"],
                    "language": source_config["language"],
                    "timestamp": published,
                }
            )
    return results


def parse_html(content: bytes, source_config: dict, encoding: str | None) -> tuple[list[dict], bool]:
    soup = BeautifulSoup(content, "lxml", from_encoding=encoding)
    selectors = [selector.strip() for selector in source_config["selector"].split(",")]
    elements = []
    used_fallback = False
    max_items = source_config.get("max_items", 10)

    for selector in selectors:
        found = soup.select(selector)
        if found:
            for element in found:
                if element not in elements:
                    elements.append(element)
            if len(elements) >= max_items:
                break

    if not elements:
        used_fallback = True
        elements = soup.find_all(["h1", "h2", "h3"])

    results: list[dict] = []
    seen_headlines: set[str] = set()
    for element in elements[:max_items]:
        headline = normalize_text(element.get_text())
        if headline in seen_headlines:
            continue

        link_tag = element if element.name == "a" else element.find("a")
        if not link_tag:
            link_tag = element.find_parent("a")
        if not link_tag:
            container = element.find_parent(["div", "li", "section", "article"])
            if container:
                link_tag = container.find("a")

        link = urljoin(source_config["url"], link_tag["href"]) if link_tag and link_tag.has_attr("href") else source_config["url"]
        if is_valid_headline(headline, link, source_config["url"]):
            results.append(
                {
                    "headline": headline,
                    "link": link,
                    "source": source_config["name"],
                    "language": source_config["language"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            seen_headlines.add(headline)

    return results, used_fallback


def list_news_sources() -> list[dict]:
    return [{"name": source["name"], "language": source["language"], "type": source["type"]} for source in SOURCES]


def _resolve_sources(source_query: str | None) -> list[dict]:
    if not source_query:
        return SOURCES
    return [source for source in SOURCES if source_query.lower() in source["name"].lower()]


def fetch_source(source: dict, limit: int | None = None) -> tuple[list[dict], dict]:
    stats = {
        "name": source["name"],
        "extracted": 0,
        "status": "Success",
        "fallback": False,
    }
    source_config = source.copy()
    if limit:
        source_config["max_items"] = limit

    try:
        content, encoding = fetch_url_with_rate_limit(source["url"])
        if not content:
            stats["status"] = "Fetch Failed"
            return [], stats

        if source["type"] == "rss":
            items = parse_rss(content, source_config)
        else:
            items, used_fallback = parse_html(content, source_config, encoding)
            stats["fallback"] = used_fallback

        stats["extracted"] = len(items)
        return items, stats
    except HTTPError as error:
        stats["status"] = f"HTTP {error.response.status_code}"
    except RequestException:
        stats["status"] = "Network Error"
    except Exception as error:
        stats["status"] = f"Error: {type(error).__name__}"
    return [], stats


def crawl_news(source_query: str | None = None, dry_run: bool = False, limit: int | None = None) -> dict:
    active_sources = _resolve_sources(source_query)
    if source_query and not active_sources:
        return {
            "status": "no_match",
            "message": f"No source matching '{source_query}' was found.",
            "saved": 0,
            "headlines": [],
            "summary": [],
        }

    seen_hashes = news_storage.load_seen_hashes()
    all_raw: list[dict] = []
    summary_stats: list[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_source, source, limit): source for source in active_sources}
        for future in as_completed(futures):
            items, stats = future.result()
            all_raw.extend(items)
            summary_stats.append(stats)

    unique: list[dict] = []
    duplicate_count = 0
    for record in all_raw:
        record_hash = generate_hash(record["headline"])
        if record_hash in seen_hashes:
            duplicate_count += 1
            continue
        if any(
            record["language"] == existing["language"]
            and get_similarity(record["headline"], existing["headline"]) > SIMILARITY_THRESHOLD
            for existing in unique
        ):
            duplicate_count += 1
            continue
        record["hash"] = record_hash
        unique.append(record)
        if not dry_run:
            seen_hashes.add(record_hash)

    output_file = None
    if not dry_run and unique:
        output_file = str(news_storage.append_to_jsonl(unique))
        news_storage.save_seen_hashes(seen_hashes)

    return {
        "status": "ok",
        "source_query": source_query,
        "dry_run": dry_run,
        "total_extracted": len(all_raw),
        "duplicates": duplicate_count,
        "saved": len(unique),
        "output_file": output_file,
        "headlines": unique,
        "summary": sorted(summary_stats, key=lambda item: item["name"]),
    }


def get_latest_headlines(limit: int = 10, source: str | None = None, language: str | None = None) -> dict:
    records = news_storage.read_jsonl(news_storage.get_latest_file())
    if source:
        records = [record for record in records if source.lower() in record["source"].lower()]
    if language:
        records = [record for record in records if record["language"] == language]
    records = list(reversed(records))[:limit]
    return {
        "status": "ok",
        "count": len(records),
        "headlines": records,
    }
