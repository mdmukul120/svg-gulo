#!/usr/bin/env python3
"""Download unDraw illustrations (SVG) for personal use.

Renders each listing page with a headless browser, collects every
cdn.undraw.co/illustration/*.svg URL, then downloads them politely.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "https://undraw.co"
OUT_DIR = Path("undraw_svgs")
PAGE_DELAY = 2.0      # seconds between listing pages
FILE_DELAY = 0.3      # seconds between file downloads
MAX_PAGES = 60        # safety cap
SVG_RE = re.compile(r"https://cdn\.undraw\.co/illustration/[A-Za-z0-9_\-]+\.svg")
UA = "Mozilla/5.0 (compatible; personal-undraw-backup/1.0)"


def page_url(n: int) -> str:
    return f"{BASE}/illustrations" if n == 1 else f"{BASE}/illustrations/{n}"


def collect_urls() -> list[str]:
    found: dict[str, None] = {}
    total_pages = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        n = 1
        while n <= (total_pages or MAX_PAGES):
            url = page_url(n)
            print(f"[page {n}] {url}", flush=True)
            page.goto(url, wait_until="networkidle", timeout=60000)
            # scroll to trigger lazy-loaded images
            for _ in range(8):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(400)
            html = page.content()
            text = page.inner_text("body")
            if total_pages is None:
                m = re.search(r"Page\s+\d+\s+of\s+(\d+)", text)
                total_pages = int(m.group(1)) if m else None
                print(f"  total pages: {total_pages}")
            urls = set(SVG_RE.findall(html))
            new = [u for u in urls if u not in found]
            for u in new:
                found[u] = None
            print(f"  {len(urls)} on page, {len(new)} new")
            if n == 1 and not urls:
                Path("debug_page1.html").write_text(html, encoding="utf-8")
                print("No SVG URLs found on page 1; saved debug_page1.html")
                browser.close()
                sys.exit(1)
            if total_pages is None and not new:
                break
            n += 1
            time.sleep(PAGE_DELAY)
        browser.close()
    return list(found)


def download(urls: list[str]) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    ok, failed = 0, []
    for i, u in enumerate(urls, 1):
        name = u.rsplit("/", 1)[-1]
        dest = OUT_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            ok += 1
            continue
        for attempt in range(3):
            try:
                r = s.get(u, timeout=30)
                r.raise_for_status()
                dest.write_bytes(r.content)
                ok += 1
                break
            except requests.RequestException as e:
                if attempt == 2:
                    failed.append(u)
                    print(f"  FAILED {u}: {e}")
                else:
                    time.sleep(2 * (attempt + 1))
        if i % 50 == 0:
            print(f"  downloaded {i}/{len(urls)}", flush=True)
        time.sleep(FILE_DELAY)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"total": len(urls), "ok": ok, "failed": failed}, indent=2)
    )
    print(f"Done. ok={ok} failed={len(failed)}")


if __name__ == "__main__":
    all_urls = collect_urls()
    print(f"Collected {len(all_urls)} SVG URLs")
    download(all_urls)
