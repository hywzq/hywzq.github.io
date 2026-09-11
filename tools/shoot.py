#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screenshot helper for the homepage.

Renders pages with headless Chrome over file:// (localhost is not reachable
from the sandboxed browser) and writes PNGs next to this script.

    python3 tools/shoot.py                 # all pages, English, 1440px
    python3 tools/shoot.py index.html 430  # one page, phone width
    python3 tools/shoot.py index.html 1440 --zh   # forced Chinese

The Chinese variant is produced by writing a temporary copy of the page with
lang-zh baked in and main.js removed, because main.js would otherwise restore
the English preference from localStorage.
"""

import os
import re
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "shots")

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PAGES = ["index.html", "publications.html", "research.html", "research-highlights.html"]


def shoot(page, width, height, zh=False):
    src = os.path.join(ROOT, page)
    if not os.path.exists(src):
        print("skip (missing):", page)
        return None

    target = src
    tmp = None
    if zh:
        with open(src, encoding="utf-8") as fh:
            html = fh.read()
        html = html.replace('<body class="lang-en"', '<body class="lang-zh"')
        html = html.replace('<body class="lang-zh"', '<body class="lang-zh"', 1)
        html = re.sub(r'\s*<script src="assets/main\.js"></script>', "", html)
        tmp = os.path.join(ROOT, "_shoot_tmp.html")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(html)
        target = tmp

    os.makedirs(OUT, exist_ok=True)
    name = page.replace(".html", "") + ("-zh" if zh else "") + "-%d.png" % width
    dest = os.path.join(OUT, name)

    url = "file://" + urllib.parse.quote(target)
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--force-device-scale-factor=1",
            "--window-size=%d,%d" % (width, height),
            "--screenshot=" + dest,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if tmp and os.path.exists(tmp):
        os.remove(tmp)
    print("wrote", os.path.relpath(dest, ROOT), os.path.getsize(dest), "bytes")
    return dest


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    zh = "--zh" in sys.argv
    if args:
        page = args[0]
        width = int(args[1]) if len(args) > 1 else 1440
        shoot(page, width, 2600 if width > 700 else 1800, zh)
    else:
        for p in PAGES:
            shoot(p, 1440, 2600)
