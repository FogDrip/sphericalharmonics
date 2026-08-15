#!/usr/bin/env python3
"""Rewrite the latest-post card in index.html from the Substack RSS feed.

Run locally with `python3 scripts/update_latest_post.py`; a scheduled GitHub
Action runs the same command and commits the result when it changes.
"""

import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://sphericalharmonics.substack.com/feed"
PAGE = Path(__file__).resolve().parent.parent / "index.html"
START = "<!-- LATEST-POST:START -->"
END = "<!-- LATEST-POST:END -->"
INDENT = " " * 16


def fetch_latest():
    req = urllib.request.Request(FEED, headers={"User-Agent": "sphericalharmonics.org site builder"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        feed = ET.fromstring(resp.read())

    item = feed.find("channel/item")
    if item is None:
        raise SystemExit("no items in feed")

    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    if not title or not link:
        raise SystemExit("feed item is missing a title or link")

    dek = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()

    pub = item.findtext("pubDate")
    try:
        date = parsedate_to_datetime(pub) if pub else None
    except (TypeError, ValueError):
        date = None

    return title, link, dek, date


def render(title, link, dek, date: datetime | None):
    dateline = "Latest post"
    if date is not None:
        dateline += f" &middot; {date.strftime('%B')} {date.day}, {date.year}"

    lines = [
        START,
        '<div class="post-card">',
        f'    <p class="dateline">{dateline}</p>',
        f'    <h3><a href="{html.escape(link, quote=True)}">{html.escape(title)}</a></h3>',
    ]
    if dek:
        lines.append(f"    <p>{html.escape(dek)}</p>")
    lines += ["</div>", END]
    return "\n".join(INDENT + line for line in lines).lstrip()


def main():
    page = PAGE.read_text()
    pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(page):
        raise SystemExit(f"markers {START} / {END} not found in {PAGE.name}")

    block = render(*fetch_latest())
    updated = pattern.sub(lambda _: block, page, count=1)

    if updated == page:
        print("latest post unchanged")
        return 0

    PAGE.write_text(updated)
    print("updated latest post")
    return 0


if __name__ == "__main__":
    sys.exit(main())
