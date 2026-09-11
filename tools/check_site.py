#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Site integrity check for the personal homepage.

Verifies, across every .html page:
  1. internal links and #anchors resolve
  2. <span class="en"> / <span class="zh"> counts are balanced
  3. CSS braces are balanced and no selector list has a stray comma
  4. no leftover placeholder text
  5. no descendant selectors like ".x span" that would pill-wrap bilingual spans
  6. the metrics pipeline files exist and agree with each other

Run:  python3 tools/check_site.py
Exit code 0 = clean, 1 = problems found.
"""

import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS_FILES = ["assets/theme.css", "assets/palettes.css", "assets/about.css", "assets/pages.css"]

# Selectors whose descendants are bilingual <span class="en">/<span class="zh">
# wrappers: a bare descendant selector would turn them into pills/chips.
PILL_SELECTOR_RE = re.compile(
    r'^\.(tag-row|method-tags|paper-tags|publication-metric|research-metric)\s+span\b'
)

PLACEHOLDERS = [
    "Lorem ipsum", "TODO", "TBD", "Your Name", "example.com",
    "xxx@", "PLACEHOLDER", "占位",
]

problems = []
notes = []


def fail(msg):
    problems.append(msg)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- pages ----
html_files = sorted(
    f for f in os.listdir(ROOT) if f.endswith(".html") and not f.startswith("_")
)
pages = {f: read(os.path.join(ROOT, f)) for f in html_files}
notes.append("pages: " + ", ".join(html_files))

# 1. internal links + anchors -------------------------------------------------
for name, html in pages.items():
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith(("http://", "https://", "mailto:", "//")):
            continue
        target, _, frag = href.partition("#")
        if not target:
            if frag and frag not in ids:
                fail("%s: dead anchor #%s" % (name, frag))
            continue
        path = os.path.normpath(os.path.join(ROOT, target))
        if not os.path.exists(path):
            fail("%s: broken link %s" % (name, href))
            continue
        if frag and os.path.basename(path) in pages:
            if frag not in set(re.findall(r'\sid="([^"]+)"', pages[os.path.basename(path)])):
                fail("%s: dead anchor %s" % (name, href))

# 2. bilingual span balance ---------------------------------------------------
for name, html in pages.items():
    en = len(re.findall(r'<span class="en"', html))
    zh = len(re.findall(r'<span class="zh"', html))
    if en != zh:
        fail("%s: unbalanced bilingual spans (en=%d zh=%d)" % (name, en, zh))
    # every .en/.zh must be closed on the same line (they are inline leaves)
    for line_no, line in enumerate(html.splitlines(), 1):
        for cls in ("en", "zh"):
            opened = line.count('<span class="%s"' % cls)
            closed = len(re.findall(r'<span class="%s"[^>]*>.*?</span>' % cls, line))
            if opened != closed:
                fail("%s:%d: unterminated <span class=\"%s\">" % (name, line_no, cls))

# 3. CSS sanity ---------------------------------------------------------------
for rel in CSS_FILES:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        fail("missing stylesheet %s" % rel)
        continue
    css = read(path)
    if css.count("{") != css.count("}"):
        fail("%s: unbalanced braces (%d { vs %d })" % (rel, css.count("{"), css.count("}")))
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # ", {" means an empty selector in the list -> whole rule is dropped
    for m in re.finditer(r',\s*\{', stripped):
        fail("%s: stray comma before '{' near offset %d" % (rel, m.start()))
    for line_no, line in enumerate(stripped.splitlines(), 1):
        head = line.split("{")[0].strip()
        if head and PILL_SELECTOR_RE.match(head):
            fail("%s:%d: descendant selector would pill-wrap bilingual spans: %s" % (rel, line_no, head))

# 4. placeholders (scan visible text only - HTML attributes such as
#    placeholder="..." are legitimate and must not be flagged) ------------------
for name, html in pages.items():
    visible = re.sub(r"<[^>]+>", " ", html)
    for token in PLACEHOLDERS:
        if token.lower() in visible.lower():
            fail("%s: placeholder text %r" % (name, token))

# 5. metrics pipeline consistency --------------------------------------------
mjson = os.path.join(ROOT, "assets", "metrics.json")
mjs = os.path.join(ROOT, "assets", "metrics-data.js")
if not os.path.exists(mjson) or not os.path.exists(mjs):
    fail("metrics pipeline incomplete (metrics.json / metrics-data.js missing)")
else:
    payload = json.loads(read(mjson))
    js = read(mjs)
    for key in ("citations", "hIndex", "i10Index"):
        val = payload["scholar"][key]
        if str(val) not in js:
            fail("metrics-data.js does not carry %s=%s" % (key, val))
    notes.append(
        "metrics: %d citations / h %d / i10 %d / %d works, updated %s"
        % (
            payload["scholar"]["citations"],
            payload["scholar"]["hIndex"],
            payload["scholar"]["i10Index"],
            payload.get("works") or 0,
            payload["updatedDisplay"],
        )
    )
    index = pages.get("index.html", "")
    for hook in ("data-metric=\"citations\"", "data-metric=\"hIndex\"", "data-metric=\"i10Index\""):
        if hook not in index:
            fail("index.html is missing the live hook %s" % hook)
    for tag in ("assets/metrics-data.js", "assets/metrics.js"):
        if tag not in index:
            fail("index.html does not load %s" % tag)
    # the hard-coded fallback numbers should match the current data
    for hook, key in (("gs-citations", "citations"), ("gs-hindex", "hIndex"), ("gs-i10index", "i10Index")):
        m = re.search(r'id="%s"[^>]*>([\d,]+)<' % hook, index)
        if m and m.group(1).replace(",", "") != str(payload["scholar"][key]):
            notes.append(
                "fallback for %s is %s but live value is %s (JS overwrites it)"
                % (key, m.group(1), payload["scholar"][key])
            )

# ----------------------------------------------------------------- report ----
for n in notes:
    print("  .", n)
if problems:
    print("\n%d PROBLEM(S):" % len(problems))
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("\nAll checks passed.")
