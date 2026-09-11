#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresh the Google Scholar metrics shown on the homepage.

Google Scholar has no public API, it blocks datacenter IPs and it sends no CORS
headers, so a static page cannot read it from the browser. What *does* work is
scraping it from this machine with a real browser engine, which is what this
script does. It writes ``assets/metrics-data.js``, which the page loads with a
plain <script> tag (so it also works when the site is opened over file://).

Usage
-----
    python3 tools/refresh_metrics.py              # scrape and write
    python3 tools/refresh_metrics.py --check      # print, do not write
    python3 tools/refresh_metrics.py --quiet      # only report on change

Exit codes: 0 = ok (file written or unchanged), 1 = scrape failed (file left as-is).
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

SCHOLAR_USER = "tv_6I4YAAAAJ"
SCHOLAR_URL = "https://scholar.google.com/citations?user=%s&hl=en" % SCHOLAR_USER
PROFILE_URL = "https://scholar.google.com/citations?user=%s" % SCHOLAR_USER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JS = os.path.join(ROOT, "assets", "metrics-data.js")
OUT_JSON = os.path.join(ROOT, "assets", "metrics.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

MAX_WORK_PAGES = 12  # Scholar paginates 20 works at a time


def find_chrome():
    # CHROME_PATH / CHROME_BIN let CI (e.g. browser-actions/setup-chrome) point
    # us at a browser that is not in any of the well-known locations.
    for var in ("CHROME_PATH", "CHROME_BIN"):
        override = os.environ.get(var)
        if override and os.path.exists(override):
            return override
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def dump_dom(chrome, url, timeout=90):
    """Render a URL with headless Chrome and return the resulting DOM."""
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--disable-extensions",
        "--virtual-time-budget=8000",
        "--user-agent=" + UA,
        "--dump-dom",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.stdout or ""


def to_int(text):
    digits = re.sub(r"[^0-9]", "", text or "")
    return int(digits) if digits else None


def parse_metrics(dom):
    """Pull the citation table out of a Scholar profile page."""
    table = re.search(r'id="gsc_rsb_st".*?</table>', dom, re.S)
    if not table:
        return None, "metrics table not found (profile page may be blocked or changed)"

    rows = {}
    since_label = None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S):
        cells = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if cells[0].lower().startswith("since"):
            since_label = cells[0]
            continue
        if len(cells) >= 3:
            rows[cells[0].lower()] = (to_int(cells[1]), to_int(cells[2]))

    citations = rows.get("citations")
    h_index = rows.get("h-index")
    i10_index = rows.get("i10-index")
    if not citations or not h_index or not i10_index:
        return None, "could not parse all three metrics rows (got %r)" % (rows,)

    return {
        "sinceLabel": since_label or "Since %d" % (datetime.date.today().year - 5),
        "citations": citations[0],
        "citationsSince": citations[1],
        "hIndex": h_index[0],
        "hIndexSince": h_index[1],
        "i10Index": i10_index[0],
        "i10IndexSince": i10_index[1],
    }, None


def count_works(chrome, first_dom):
    """Count how many works the Scholar profile lists, across all pages."""
    total = len(re.findall(r'class="gsc_a_tr"', first_dom))
    if total == 0:
        return None
    cstart = 20
    while cstart < MAX_WORK_PAGES * 20:
        dom = dump_dom(chrome, "%s&cstart=%d" % (SCHOLAR_URL, cstart))
        n = len(re.findall(r'class="gsc_a_tr"', dom))
        if n == 0:
            break
        total += n
        if n < 20:
            break
        cstart += 20
    return total


def build_payload(metrics, works):
    now = datetime.datetime.now().astimezone()
    return {
        "source": "Google Scholar",
        "profile": PROFILE_URL,
        "updated": now.isoformat(timespec="seconds"),
        "updatedDisplay": now.strftime("%d %B %Y"),
        "scholar": metrics,
        "works": works,
    }


def render_js(payload):
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "/* Generated by tools/refresh_metrics.py - do not edit by hand. */\n"
        "/* Source: Google Scholar profile %s */\n"
        "window.__SCHOLAR_METRICS__ = %s;\n" % (PROFILE_URL, body)
    )


def read_previous():
    if not os.path.exists(OUT_JSON):
        return None
    try:
        with open(OUT_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def summarise(payload):
    s = payload["scholar"]
    return "citations %d (since %s) | h-index %d | i10-index %d | works %s" % (
        s["citations"], s["citationsSince"], s["hIndex"], s["i10Index"], payload["works"],
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print the scraped values without writing")
    ap.add_argument("--quiet", action="store_true", help="stay silent unless something changed")
    args = ap.parse_args()

    def say(msg):
        if not args.quiet:
            print(msg)

    chrome = find_chrome()
    if not chrome:
        print("ERROR: no Chrome/Chromium binary found; cannot scrape Google Scholar.", file=sys.stderr)
        return 1
    say("Using browser: %s" % chrome)

    try:
        dom = dump_dom(chrome, SCHOLAR_URL)
    except subprocess.TimeoutExpired:
        print("ERROR: timed out fetching the Scholar profile.", file=sys.stderr)
        return 1

    metrics, err = parse_metrics(dom)
    if err:
        print("ERROR: %s" % err, file=sys.stderr)
        print("       (leaving existing metrics in place)", file=sys.stderr)
        return 1

    works = count_works(chrome, dom)
    payload = build_payload(metrics, works)

    previous = read_previous()
    if previous and previous.get("scholar") == payload["scholar"] and previous.get("works") == payload["works"]:
        # Numbers unchanged: only refresh the timestamp so "last checked" stays honest.
        changed = False
    else:
        changed = True

    say("Scraped: %s" % summarise(payload))
    if previous and changed:
        say("Previous: %s" % summarise(previous))

    if args.check:
        say("(--check: nothing written)")
        return 0

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(OUT_JS, "w", encoding="utf-8") as fh:
        fh.write(render_js(payload))

    if changed:
        say("Updated %s and %s" % (os.path.relpath(OUT_JSON, ROOT), os.path.relpath(OUT_JS, ROOT)))
    else:
        say("Numbers unchanged; timestamp refreshed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
