import os
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Iterable
from pathlib import Path
from newsapi import NewsApiClient

def fetch_news(topics: Iterable[str], max_articles: int = 6, days_back: int = 1, fallback_headlines: bool = True) -> List[Dict]:
    """
    Fetch recent news matching any of the provided topics.

    - topics: iterable of query terms (OR-joined)
    - max_articles: max articles to return
    - days_back: look back this many days for 'everything' endpoint
    - fallback_headlines: if everything returns nothing, try top-headlines
    """
    key = os.environ.get("NEWSAPI_KEY")
    if not key:
        logging.error("NEWSAPI_KEY environment variable not set")
        raise RuntimeError("NEWSAPI_KEY environment variable not set")

    api = NewsApiClient(api_key=key)
    query = " OR ".join(topics)

    from_dt = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    # NewsAPI expects "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS" (no timezone offset)
    from_param = from_dt.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        resp = api.get_everything(q=query, language="en", sort_by="publishedAt",
                                  page_size=max_articles, from_param=from_param)
        articles = resp.get("articles", []) or []
    except Exception as exc:
        logging.exception("Error fetching 'everything' from NewsAPI: %s", exc)
        articles = []

    # fallback to top-headlines if nothing found and fallback enabled
    if not articles and fallback_headlines:
        try:
            resp = api.get_top_headlines(q=query, language="en", page_size=max_articles)
            articles = resp.get("articles", []) or []
        except Exception as exc:
            logging.exception("Error fetching 'top-headlines' from NewsAPI: %s", exc)
            articles = []

    cleaned = []
    seen_urls = set()
    for a in articles:
        url = a.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        cleaned.append({
            "title": (a.get("title") or "").strip(),
            "url": url,
            "source": (a.get("source") or {}).get("name", ""),
            "summary": (a.get("description") or "") or ""
        })
        if len(cleaned) >= max_articles:
            break

    # Also save raw fetched news into /out for inspection
    try:
        out_dir = Path(__file__).resolve().parents[1] / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        news_path = out_dir / "news.json"
        with open(news_path, "w", encoding="utf-8") as nf:
            json.dump(articles, nf, ensure_ascii=False, indent=2)
        print(f"Wrote fetched news to {news_path}")
    except Exception:
        # Don't let a write error break the fetching pipeline
        pass

    return cleaned