import asyncio
import os
import sys

# Ensure backend directory is in path
sys.path.append(os.getcwd())

import main
from main import NewsCrawlRequest

async def run_crawl():
    print("Starting targeted crawl for Uttar Pradesh...")
    # This calls the same logic the UI uses
    request = NewsCrawlRequest(source_query="Uttar Pradesh", limit=25)
    result = await main.news_crawl(request)
    print(f"Crawl finished. Saved {result.get('saved', 0)} new headlines.")
    
    # Also crawl national news to extract UP-related mentions
    print("Starting national crawl for additional UP context...")
    request_nat = NewsCrawlRequest(source_query="Jagran Hindi", limit=20)
    await main.news_crawl(request_nat)

if __name__ == "__main__":
    asyncio.run(run_crawl())
