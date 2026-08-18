#!/usr/bin/env python3
"""Rewrite the latest-post card in index.html from the Substack RSS feed.

Run locally with `python3 scripts/update_latest_post.py`; a scheduled GitHub
Action runs the same command and commits the result when it changes.

Substack sits behind a Cloudflare challenge that 403s datacenter IPs (including
GitHub Actions runners), so the feed is read through a chain of sources and the
script leaves the page untouched — exit 0, no commit — when every source fails,
keeping the last-known-good card rather than blanking it.
"""

import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

PUBLICATION = "https://sphericalharmonics.substack.com"
FEED = f"{PUBLICATION}/feed"
RSS2JSON = "https://api.rss2json.com/v1/api.json?rss_url=" + urllib.parse.quote(FEED, safe="")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

PAGE = Path(__file__).resolve().parent.parent / "index.html"
START = "<!-- LATEST-POST:START -->"
END = "<!-- LATEST-POST:END -->"
INDENT = " " * 16


def get(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_date(raw):
    """Accept RFC 822 (Substack) and 'YYYY-MM-DD HH:MM:SS' (rss2json)."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def from_rss():
    item = ET.fromstring(get(FEED, "application/rss+xml, application/xml")).find("channel/item")
    if item is None:
        raise ValueError("feed has no items")
    return {
        "title": (item.findtext("title") or "").strip(),
        "link": (item.findtext("link") or "").strip(),
        "dek": strip_tags(item.findtext("description")),
        "date": parse_date(item.findtext("pubDate")),
    }


def from_rss2json():
    payload = json.loads(get(RSS2JSON, "application/json"))
    if payload.get("status") != "ok" or not payload.get("items"):
        raise ValueError(f"rss2json returned {payload.get('status')!r} with no items")
    item = payload["items"][0]
    return {
        "title": (item.get("title") or "").strip(),
        "link": (item.get("link") or "").strip(),
        "dek": strip_tags(item.get("description")),
        "date": parse_date(item.get("pubDate")),
    }


def fetch_latest():
    """Return the newest post, or None if every source is unreachable."""
    for name, source in (("substack rss", from_rss), ("rss2json", from_rss2json)):
        try:
            post = source()
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError,
                json.JSONDecodeError, ValueError, TimeoutError, OSError) as exc:
            print(f"  {name}: unavailable ({exc.__class__.__name__}: {exc})")
            continue
        if post["title"] and post["link"]:
            print(f"  {name}: ok")
            return post
        print(f"  {name}: item missing a title or link")
    return None


def render(post):
    dateline = "Latest post"
    if post["date"] is not None:
        d = post["date"]
        dateline += f" &middot; {d.strftime('%B')} {d.day}, {d.year}"

    lines = [
        START,
        '<div class="post-card">',
        f'    <p class="dateline">{dateline}</p>',
        f'    <h3><a href="{html.escape(post["link"], quote=True)}">{html.escape(post["title"])}</a></h3>',
    ]
    if post["dek"]:
        lines.append(f'    <p>{html.escape(post["dek"])}</p>')
    lines += ["</div>", END]
    return "\n".join(INDENT + line for line in lines).lstrip()


def main():
    page = PAGE.read_text()
    pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(page):
        print(f"error: markers {START} / {END} not found in {PAGE.name}", file=sys.stderr)
        return 1

    post = fetch_latest()
    if post is None:
        # Every source failed. Keep the last-known-good card rather than
        # blanking it, and don't fail the build over someone else's outage.
        print("no feed source reachable; leaving the existing card in place")
        return 0

    block = render(post)
    updated = pattern.sub(lambda _: block, page, count=1)
    if updated == page:
        print(f"latest post unchanged: {post['title']}")
        return 0

    PAGE.write_text(updated)
    print(f"updated latest post: {post['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
