"""
Scrape Kazakh-language articles from kaz.tengrinews.kz.

Discovers article URLs from category listing pages, then extracts
structured data (title, body, category, date) from the JSON-LD
embedded in each article page.

Usage:
    python3 eval/scraper.py --output data/corpus/articles.jsonl --limit 3000
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit(
        "Missing dependencies.  Install with:\n"
        "  pip install requests beautifulsoup4\n"
        "or:\n"
        "  uv pip install requests beautifulsoup4"
    )

BASE = "https://kaz.tengrinews.kz"
CATEGORIES = [
    "/news/",
    "/kazakhstan_news/",
    "/crime/",
    "/world_news/",
    "/sport/",
]
HEADERS = {
    "User-Agent": "pg-kazsearch-eval/1.0 (research; +https://github.com/darkhanakh/pg-kazsearch)",
    "Accept-Language": "kk,ru;q=0.5",
}
DELAY = 0.5


def _fetch(url: str, session: requests.Session, retries: int = 2) -> str | None:
    for attempt in range(1, retries + 2):
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt <= retries:
                time.sleep(DELAY * attempt)
            else:
                print(f"  WARN: {url} -> {e}", file=sys.stderr)
    return None


def _extract_article_urls(page_html: str) -> list[str]:
    soup = BeautifulSoup(page_html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/[a-z_]+/[a-z0-9_-]+-\d+/$", href):
            full = urljoin(BASE, href)
            if full.startswith(BASE) and full not in urls:
                urls.append(full)
    return urls


def _parse_jsonld(page_html: str) -> dict | None:
    soup = BeautifulSoup(page_html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        graph = data.get("@graph", data)
        if isinstance(graph, list):
            for item in graph:
                if item.get("@type") == "NewsArticle":
                    return item
        elif isinstance(graph, dict):
            if "headline" in graph or "articleBody" in graph:
                return graph
    return None


def _clean_body(raw: str) -> str:
    text = html.unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_article(page_html: str, url: str) -> dict | None:
    ld = _parse_jsonld(page_html)
    if not ld:
        return None

    title = ld.get("headline", "").strip()
    body = _clean_body(ld.get("articleBody", ""))
    if not title or not body or len(body) < 50:
        return None

    date = ""
    dp = ld.get("datePublished", "")
    m = re.match(r"\d{4}-\d{2}-\d{2}", dp)
    if m:
        date = m.group(0)

    category = ld.get("articleSection", "")
    if not category:
        breadcrumbs = ld.get("itemListElement") or []
        if breadcrumbs and len(breadcrumbs) >= 3:
            category = breadcrumbs[-1].get("name", "")

    return {
        "url": url,
        "title": title,
        "body": body,
        "category": category,
        "date": date,
    }


def _progress(msg: str):
    sys.stdout.write(f"\r\033[K{msg}")
    sys.stdout.flush()


def discover_urls(session: requests.Session, limit: int) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    for cat in CATEGORIES:
        if len(urls) >= limit:
            break
        cat_url = urljoin(BASE, cat)
        _progress(f"[discover] {cat} page 1 ...")
        page_html = _fetch(cat_url, session)
        if not page_html:
            continue
        for u in _extract_article_urls(page_html):
            if u not in seen:
                seen.add(u)
                urls.append(u)
        time.sleep(DELAY)

        consecutive_empty = 0
        for page_num in range(2, 300):
            if len(urls) >= limit:
                break
            _progress(f"[discover] {cat} page {page_num} | {len(urls)} URLs")
            page_url = urljoin(BASE, f"{cat}page/{page_num}/")
            page_html = _fetch(page_url, session)
            if not page_html:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                continue
            new_urls = _extract_article_urls(page_html)
            added = 0
            for u in (new_urls or []):
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
                    added += 1
            if added == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                continue
            consecutive_empty = 0
            time.sleep(DELAY)

    _progress(f"[discover] homepage ...")
    home_html = _fetch(BASE + "/", session)
    if home_html:
        for u in _extract_article_urls(home_html):
            if u not in seen:
                seen.add(u)
                urls.append(u)

    print(f"\r\033[K[discover] done: {len(urls)} unique URLs")
    return urls[:limit]


def load_existing(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                seen.add(obj.get("url", ""))
            except json.JSONDecodeError:
                pass
    return seen


def main():
    parser = argparse.ArgumentParser(description="Scrape Kazakh articles from kaz.tengrinews.kz")
    parser.add_argument("--output", default="data/corpus/articles.jsonl")
    parser.add_argument("--limit", type=int, default=3000, help="Max articles to scrape")
    parser.add_argument("--resume", action="store_true", help="Skip already-scraped URLs")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_existing(out_path) if args.resume else set()
    if existing:
        print(f"Resuming: {len(existing)} articles already scraped")

    session = requests.Session()
    article_urls = discover_urls(session, args.limit + len(existing))
    article_urls = [u for u in article_urls if u not in existing]
    print(f"Will fetch {len(article_urls)} articles (target: {args.limit})")

    mode = "a" if args.resume else "w"
    scraped = len(existing)
    skipped = 0
    t0 = time.monotonic()
    with out_path.open(mode, encoding="utf-8") as f:
        for i, url in enumerate(article_urls):
            if scraped >= args.limit:
                break

            elapsed = time.monotonic() - t0
            rate = scraped / elapsed if elapsed > 1 else 0
            eta = int((args.limit - scraped) / rate) if rate > 0 else 0
            _progress(
                f"[fetch] {scraped}/{args.limit}  "
                f"skip={skipped}  "
                f"{rate:.1f} art/s  "
                f"ETA {eta // 60}m{eta % 60:02d}s"
            )

            page_html = _fetch(url, session)
            if not page_html:
                skipped += 1
                continue

            article = parse_article(page_html, url)
            if not article:
                skipped += 1
                continue

            f.write(json.dumps(article, ensure_ascii=False) + "\n")
            f.flush()
            scraped += 1
            time.sleep(DELAY)

    elapsed = time.monotonic() - t0
    print(f"\r\033[KDone: {scraped} articles in {out_path}  ({elapsed:.0f}s, skipped {skipped})")


if __name__ == "__main__":
    main()
