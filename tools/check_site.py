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
  7. every "find this paper" link is accounted for by the citation map

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

# The "find this paper" links, whose literal ?q= value keys the citation map.
QUERY_RE = re.compile(r'href="https://scholar\.google\.com/scholar\?q=([^"]+)"')

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

    # --- per-publication citation counts -------------------------------------
    # The keys of `citations` are the literal ?q= values of the "find this paper"
    # links. If a title is edited in the HTML without re-running the refresh, the
    # key goes stale and that badge silently disappears - so check both directions.
    counts = payload.get("citations")
    if counts is None:
        fail("metrics.json has no `citations` map (run tools/refresh_metrics.py)")
    else:
        on_page = set()
        for name, html in pages.items():
            on_page.update(re.findall(QUERY_RE, html))
        stale = sorted(set(counts) - on_page)
        if stale:
            fail(
                "%d citation key(s) no longer appear as ?q= links in any page "
                "(title edited? re-run tools/refresh_metrics.py): %s"
                % (len(stale), "; ".join(s[:60] for s in stale[:3]))
            )
        unmatched = sorted(on_page - set(counts))
        matches = payload.get("citationMatches") or {}
        if matches.get("matched") != len(counts):
            fail("citationMatches.matched=%s but %d keys in citations" % (matches.get("matched"), len(counts)))
        notes.append(
            "citations: %d/%d publication links have a count (%d not on Scholar yet)"
            % (len(counts), len(on_page), len(unmatched))
        )
        for name in ("publications.html", "research-highlights.html"):
            if name not in pages:
                continue
            for tag in ("assets/metrics-data.js", "assets/metrics.js"):
                if tag not in pages[name]:
                    fail("%s does not load %s" % (name, tag))
    # the hard-coded fallback numbers should match the current data
    for hook, key in (("gs-citations", "citations"), ("gs-hindex", "hIndex"), ("gs-i10index", "i10Index")):
        m = re.search(r'id="%s"[^>]*>([\d,]+)<' % hook, index)
        if m and m.group(1).replace(",", "") != str(payload["scholar"][key]):
            notes.append(
                "fallback for %s is %s but live value is %s (JS overwrites it)"
                % (key, m.group(1), payload["scholar"][key])
            )

# 6. publication counts -------------------------------------------------------
# The numbers in the hero sentence and the metric cards are counted from the list
# itself by assets/counts.js, so a stale value is cosmetic rather than fatal - but
# it is what a crawler or a no-JS reader sees, so report any drift.
pub = pages.get("publications.html")
if pub:
    GROUPS = [
        "first-and-corresponding-author",
        "under-review-and-submitted",
        "climate-dynamics-earth-system-modelling-and-paleoclimate",
        "ecology",
    ]
    IN_PROGRESS_RE = re.compile(r"under review|submitted|in revising", re.I)
    group_items = {}
    for gid in GROUPS:
        # the group's heading, then everything up to the next heading / details block
        m = re.search(
            r'<h2 id="%s".*?</h2>(.*?)(?=<h2 id=|<details|</section>|\Z)' % re.escape(gid),
            pub,
            re.S,
        )
        group_items[gid] = re.findall(r"<li\b.*?</li>", m.group(1) if m else "", re.S)

    total = sum(len(v) for v in group_items.values())
    in_progress = 0
    for items in group_items.values():
        for it in items:
            note = re.search(r'<span class="pub-note"[^>]*>(.*?)</span>', it, re.S)
            if note and IN_PROGRESS_RE.search(note.group(1)):
                in_progress += 1

    expected = {
        "first-author": len(group_items[GROUPS[0]]),
        "total": total,
        "in-progress": in_progress,
    }
    notes.append(
        "publication counts: %d first/corresponding, %d total, %d in progress"
        % (expected["first-author"], total, in_progress)
    )
    for key, actual in expected.items():
        for shown in sorted(set(re.findall(r'data-pub-count="%s"[^>]*>([\d,]+)<' % key, pub))):
            if shown.replace(",", "") != str(actual):
                notes.append(
                    "fallback for pub-count %s is %s but the list has %d "
                    "(assets/counts.js overwrites it)" % (key, shown, actual)
                )

# 7. publication-count claims on the other pages ------------------------------
# publications.html derives its numbers from the list itself (assets/counts.js).
# The other pages cannot - there is no list on them - so their numbers are
# hand-written and drift silently. This is NOT a cosmetic fallback like section
# 6: nothing overwrites these at runtime, so a stale value is what the reader
# actually sees. Treat drift as a failure.
if pub:
    claims = [
        (
            re.compile(r"([\d,]{1,4})\s*(?:journal papers|篇期刊论文)", re.I),
            total,
            "journal papers",
        ),
        (
            re.compile(
                r"([\d,]{1,4})\s*(?:first- and corresponding-author papers|"
                r"第一作者与通讯作者论文)",
                re.I,
            ),
            len(group_items[GROUPS[0]]),
            "first/corresponding-author papers",
        ),
    ]
    for name, html in pages.items():
        if name == "publications.html":
            continue
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        for rx, want, label in claims:
            for m in rx.finditer(text):
                shown = m.group(1).replace(",", "")
                if shown != str(want):
                    fail(
                        "%s: says %s %s but the list has %d"
                        % (name, shown, label, want)
                    )

# 8. paper cards / study summaries vs the publication list --------------------
# research-highlights.html (study summaries) and research.html (the paper cards
# under each direction) both restate a paper's journal and status. The count
# check (7) cannot see that, and this is exactly how the pages drifted on
# 2026-09-28: the list said "Science Advances / Under review" while both pages
# still said "Nature Climate Change / submitted".
if pub:
    pub_entries = []
    for gid in GROUPS:
        m = re.search(
            r'<h2 id="%s".*?</h2>(.*?)(?=<h2 id=|<details|</section>|\Z)' % re.escape(gid),
            pub,
            re.S,
        )
        for li in re.findall(r"<li\b.*?</li>", m.group(1) if m else "", re.S):
            em = re.search(r"<em[^>]*>(.*?)</em>", li, re.S)
            note = re.search(r'<span class="pub-note"[^>]*>(.*?)</span>', li, re.S)
            pub_entries.append(
                {"text": li, "journal": em.group(1) if em else "",
                 "note": note.group(1) if note else ""}
            )

    def plain(s):
        s = re.sub(r"<[^>]+>", " ", s)
        for a, b in (("&ndash;", "-"), ("&mdash;", "-"), ("&amp;", "&"),
                     ("&#8217;", "'"), ("\u2013", "-"), ("\u2014", "-")):
            s = s.replace(a, b)
        return re.sub(r"\s+", " ", s).strip()

    def key(s):
        return re.sub(r"[^a-z0-9]+", "", plain(s).lower())

    # The card writes the state in parentheses ("… 2026 (under review)."); the
    # list writes it bare in a .pub-note span ("Under review"). Two patterns.
    CARD_STATUS_RE = re.compile(r"\((in revising|under review|submitted)\)", re.I)
    NOTE_STATUS_RE = re.compile(r"^(in revising|under review|submitted)$", re.I)

    cards = []
    hi = pages.get("research-highlights.html")
    if hi:
        studies = re.search(r'<section id="studies".*?</section>', hi, re.S)
        if studies:
            for art in re.findall(r"<article[^>]*>(.*?)</article>", studies.group(0), re.S):
                h3 = re.search(r"<h3[^>]*>(.*?)</h3>", art, re.S)
                cite = re.search(r'<p class="research-citation"[^>]*>(.*?)</p>', art, re.S)
                if h3 and cite:
                    cards.append(("research-highlights.html", h3.group(1), cite.group(1)))
    rp = pages.get("research.html")
    if rp:
        for card in re.findall(r'<article class="paper-card".*?</article>', rp, re.S):
            h3 = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
            cite = re.search(r"<p [^>]*>(.*?)</p>", card, re.S)
            if h3 and cite:
                cards.append(("research.html", h3.group(1), cite.group(1)))

    for page, title_html, cite_html in cards:
        shown_em = re.search(r"<em[^>]*>(.*?)</em>", cite_html, re.S)
        if not shown_em:
            continue
        want = key(title_html)
        listed = next((e for e in pub_entries if want and want in key(e["text"])), None)
        name = plain(title_html)[:48]
        if listed is None:
            notes.append("%s: card not in the publication list: %s" % (page, name))
            continue
        if key(shown_em.group(1)) != key(listed["journal"]):
            fail(
                "%s: '%s' says %s but the list says %s"
                % (page, name, plain(shown_em.group(1)), plain(listed["journal"]))
            )
        # Status only counts as a status if it is one of the review states -
        # "In Chinese" / "Highly Cited Paper" are annotations, not states, and
        # the cards are not expected to carry them.
        head = cite_html.split('<span class="en"')[0]
        shown_status = CARD_STATUS_RE.search(plain(head))
        listed_status = NOTE_STATUS_RE.search(plain(listed["note"]).strip())
        if shown_status and listed_status:
            if shown_status.group(1).lower() != listed_status.group(1).lower():
                fail(
                    "%s: '%s' says (%s) but the list says %s"
                    % (page, name, shown_status.group(1), plain(listed["note"]))
                )
        elif shown_status and not listed_status:
            fail(
                "%s: '%s' says (%s) but the list carries no such status"
                % (page, name, shown_status.group(1))
            )
        elif listed_status and not shown_status:
            notes.append(
                "%s: '%s' is %s in the list but the card shows no status"
                % (page, name, plain(listed["note"]))
            )

# 9. document outline ---------------------------------------------------------
# Every page needs exactly one <h1>. research.html once had none at all and used
# a large bold paragraph as a stand-in title - which is how a body paragraph
# ended up rendering larger than every section heading on the page.
for name, html in pages.items():
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if len(h1s) != 1:
        fail("%s: expected exactly one <h1>, found %d" % (name, len(h1s)))
    elif not plain(h1s[0]).strip():
        fail("%s: <h1> is empty" % name)

# ----------------------------------------------------------------- report ----
for n in notes:
    print("  .", n)
if problems:
    print("\n%d PROBLEM(S):" % len(problems))
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("\nAll checks passed.")
