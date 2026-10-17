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
  6. every derived number is anchored and in step with the content
  7. no count is typed straight into a sentence, bypassing the anchors
  8. every paper card / study summary matches the publication list
  9. each page has exactly one <h1>
 10. the "Papers by Year" block adds up
 11. each multi-"Wang Z." entry bolds the right author

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

# 6. derived numbers ----------------------------------------------------------
# Every count on the site is anchored in the HTML with data-fact="<key>", and
# every value comes from one place: tools/site_facts.py counts it from the
# content, tools/build_counts.py writes it into the anchor (the no-JS fallback)
# and into assets/counts-data.js (which assets/counts.js applies at runtime).
# Nothing is hand-maintained, so there is nothing to verify by hand here - we
# just ask the builder whether the pages are in step. That covers the hero
# numbers, the metric tiles, the Model Data tile and "Papers by Year" at once.
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_counts  # noqa: E402
import site_facts as sf  # noqa: E402

# still needed by the card / by-year / author checks further down
pub = pages.get("publications.html")
GROUPS = sf.GROUPS
group_items = sf.group_items(pub) if pub else {}

facts, _by_year, built, build_problems = build_counts.build(ROOT)

for name in sorted(built):
    if built[name] != pages.get(name):
        fail("%s: a [data-fact] anchor is out of step with the content "
             "(run: python3 tools/build_counts.py)" % name)
for msg in build_problems:
    fail("counts: %s" % msg)

notes.append(
    "counts: %d journal papers, %d first/corresponding-author, %d in progress, "
    "%d highly cited, %d CMIP6 datasets, %d research directions"
    % (facts["journal-papers"], facts["first-author-papers"],
       facts["in-progress-papers"], facts["highly-cited-papers"],
       facts["cmip6-datasets"], facts["research-directions"])
)

# 6b. count-like claims that are NOT anchored ---------------------------------
# The builder only sees anchored numbers, so a count typed straight into a
# sentence would sail past it. Strip the anchors, then look for a digit sitting
# directly in front of a count phrase - that is a number someone forgot to tag,
# and exactly the "you changed one place and forgot another" failure this check
# exists to prevent. Each remaining tag is replaced by NUL rather than a space,
# so a number in one element ("...23</span>" in the i10 tile) cannot appear to
# be next to a phrase in the following element. A digit followed by "%" is part
# of a name ("ESI 1% highly cited paper"), not a count, so it is excluded.
ANCHOR_STRIP_RE = re.compile(r'<\w+\b[^>]*data-fact="[^"]*"[^>]*>.*?</\w+>', re.S)
UNANCHORED_CLAIM_RE = re.compile(
    r"(\d{1,4})(?!\s*%)\s{0,3}(?:journal papers|篇期刊论文|"
    r"first- and corresponding-author papers|第一作者与通讯作者论文|"
    r"highly cited paper|高被引论文|"
    r"CMIP6\s*[\u2013\u2014-]\s*PMIP4|组 CMIP6)",
    re.I,
)
for name, html in pages.items():
    bare = re.sub(r"<[^>]+>", "\x00", ANCHOR_STRIP_RE.sub(" ", html))
    for m in UNANCHORED_CLAIM_RE.finditer(bare):
        fail("%s: %r looks like an unanchored count - wrap the digit in "
             "data-fact=... so it cannot go stale" % (name, m.group(0).strip()))

# 6c. metric tiles ------------------------------------------------------------
# The tiles are where a hand-typed number is most tempting: adding one is easy,
# and nothing about the markup forces it to be wired up. So require every tile's
# <strong> to carry either data-fact (a number this site counts) or data-metric
# (a number Scholar supplies). Without one, the tile silently stops updating.
TILE_RE = re.compile(
    r'<(?:article|div)\b[^>]*class="[^"]*\b(?:scholar|research|publication)-metric\b'
    r'[^"]*"[^>]*>(.*?)</(?:article|div)>',
    re.S,
)
STRONG_NUM_RE = re.compile(r"<strong\b([^>]*)>([\d,]+)</strong>")
for name, html in pages.items():
    for tile in TILE_RE.findall(html):
        for attrs, shown in STRONG_NUM_RE.findall(tile):
            if "data-fact=" in attrs or "data-metric=" in attrs:
                continue
            fail("%s: a metric tile shows %s with neither data-fact nor "
                 "data-metric - it will go stale" % (name, shown))

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

# 10. "Papers by Year" ---------------------------------------------------------
# The year breakdown restates two things the list already knows: how many papers
# each year holds, and how many distinct journals those papers span (the first
# four are named, the rest are folded into "and N more"). The numbers themselves
# come from the anchors like everything else, so this is really a check that the
# block's *shape* still matches the list - a year with more journals than it
# names needs an "and N more".
if pub:
    per_year = {}
    for gid in GROUPS:
        for li in group_items[gid]:
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", li))
            years = re.findall(r"\b((?:19|20)\d{2})\b", text)
            em = re.search(r"<em[^>]*>(.*?)</em>", li, re.S)
            journal = plain(em.group(1)) if em else ""
            if years:
                per_year.setdefault(years[-1], {"papers": 0, "journals": set()})
                per_year[years[-1]]["papers"] += 1
                per_year[years[-1]]["journals"].add(journal)

    block = re.search(
        r'<details class="publication-group".*?</details>', pub, re.S
    )
    if not block:
        fail("publications.html: the 'Papers by Year' block is missing")
    else:
        seen = set()
        for li in re.findall(r"<li\b.*?</li>", block.group(0), re.S):
            ym = re.search(r"<strong[^>]*>((?:19|20)\d{2})</strong>", li)
            # the counts are wrapped in data-fact anchors now, so allow for the
            # opening and closing tag around the number
            cm = re.search(
                r"&mdash;\s*(?:<[^>]+>\s*)?([\d,]+)(?:\s*</[^>]+>)?\s*papers?", li
            )
            if not (ym and cm):
                fail("publications.html: unparseable 'Papers by Year' entry")
                continue
            year, shown = ym.group(1), int(cm.group(1).replace(",", ""))
            seen.add(year)
            actual = per_year.get(year)
            if not actual:
                fail("publications.html: 'Papers by Year' lists %s but the list "
                     "has no %s papers" % (year, year))
                continue
            if shown != actual["papers"]:
                fail("publications.html: 'Papers by Year' says %s has %d papers "
                     "but the list has %d" % (year, shown, actual["papers"]))
            named = re.findall(r"<em[^>]*>(.*?)</em>", li, re.S)
            more = re.search(
                r"and\s+(?:<[^>]+>\s*)?([\d,]+)(?:\s*</[^>]+>)?\s+more", li
            )
            total_journals = len(named) + (
                int(more.group(1).replace(",", "")) if more else 0
            )
            if total_journals != len(actual["journals"]):
                fail("publications.html: 'Papers by Year' accounts for %d "
                     "journals in %s but the list has %d"
                     % (total_journals, year, len(actual["journals"])))
        missing = sorted(set(per_year) - seen, reverse=True)
        if missing:
            fail("publications.html: 'Papers by Year' omits %s"
                 % ", ".join(missing))

# 11. bolded author on entries with more than one "Wang Z." -------------------
# The site marks the author in <strong>. Where a paper lists more than one
# "Wang Z." that marker cannot be inferred from the text, and it has been on
# the wrong author before. The expected 1-based position is recorded here,
# taken from the publisher record (OpenAlex, full names) and confirmed with
# the author. Adding a paper with a second "Wang Z." needs a line here.
WANG_BOLD = {
    "fbjMuifd6SFcj31TVAFBlv": 6,   # Hydrol. Earth Syst. Sci. 2026
    "AwM1NrXehPUN20eM8L53er": 8,   # J. Hydrol. 2026
    "Y4z7nAAfAkBw5VVFs954NS": 9,   # Land Degrad. Dev. 2026
    "dm0omClvOEdn7YfRpOSrBu": 9,   # Environ. Impact Assess. Rev. 2026
    "j3mztZcumk8MnegbkbwXIA": 8,   # J. Environ. Manage. 2026
    "n2xiX4BNRQT86NakgOuDNk": 5,   # J. Environ. Manage. 2025
    "CGHzWxcCnRFsKFFdycui0E": 8,   # Remote Sens. 2025
    "mf4VXF3q6vTkWiPJJWFII7": 3,   # Remote Sens. 2024
    "aETeoAnoDwd13Cdnnrp2qJ": 7,   # Earth's Future, under review
    "yrkVI42jzmugdNjI7CpCKE": 7,   # Sci. Total Environ. 2023
}
if pub:
    for li in re.findall(r"<li\b.*?</li>", pub, re.S):
        node = re.search(r'data-page-node-id="([^"]+)"', li)
        if not node:
            continue
        cut = li.find("<em")
        head = li[:cut] if cut > 0 else li
        if re.sub(r"<[^>]+>", "", head).count("Wang Z.") < 2:
            continue
        idx = li[:li.find("<strong")].count(",") + 1
        want = WANG_BOLD.get(node.group(1))
        if want is None:
            notes.append("bolded author unverified on %s (has >1 'Wang Z.', "
                         "bold at #%d) - add it to WANG_BOLD" % (node.group(1), idx))
        elif idx != want:
            fail("publications.html: %s bolds author #%d but the recorded "
                 "position for 'Wang Z.' is #%d" % (node.group(1), idx, want))

# ----------------------------------------------------------------- report ----
for n in notes:
    print("  .", n)
if problems:
    print("\n%d PROBLEM(S):" % len(problems))
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("\nAll checks passed.")
