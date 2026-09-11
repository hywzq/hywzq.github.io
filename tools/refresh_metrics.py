#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresh the Google Scholar metrics shown on the homepage.

Google Scholar has no public API, it blocks datacenter IPs and it sends no CORS
headers, so a static page cannot read it from the browser. What *does* work is
scraping it from this machine with a real browser engine, which is what this
script does. It writes ``assets/metrics-data.js``, which the page loads with a
plain <script> tag (so it also works when the site is opened over file://).

Besides the headline numbers it also records the citation count of every work on
the profile, then matches those against the "find this paper" links in the site's
own HTML so each publication can show its own count. The matches are emitted
keyed by the literal ``?q=`` value of the link, which means assets/metrics.js can
look a count up with a plain string comparison - the title-matching rules exist
only here and cannot drift out of sync with a second copy in JavaScript.

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
from urllib.parse import unquote_plus

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


WORK_ROW = re.compile(r'<tr class="gsc_a_tr">(.*?)</tr>', re.S)
WORK_TITLE = re.compile(r'class="gsc_a_at"[^>]*>(.*?)</a>', re.S)
WORK_CITED = re.compile(r'class="gsc_a_ac[^"]*"[^>]*>(.*?)</a>', re.S)
WORK_YEAR = re.compile(r'class="gsc_a_h[^"]*"[^>]*>(.*?)</span>', re.S)

ESCAPES = [("&amp;", "&"), ("&#39;", "'"), ("&apos;", "'"), ("&quot;", '"'),
           ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")]


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def unescape(s):
    for a, b in ESCAPES:
        s = s.replace(a, b)
    return s


def parse_works(dom):
    """Pull every work row out of a Scholar profile page."""
    out = []
    for row in WORK_ROW.findall(dom):
        t = WORK_TITLE.search(row)
        if not t:
            continue
        c = WORK_CITED.search(row)
        y = WORK_YEAR.search(row)
        cited = strip_tags(c.group(1)) if c else ""
        year = strip_tags(y.group(1)) if y else ""
        out.append({
            "title": unescape(strip_tags(t.group(1))),
            "citations": int(cited) if cited.isdigit() else 0,
            "year": int(year) if year.isdigit() else None,
        })
    return out


def collect_works(chrome, first_dom):
    """Every work the profile lists, with its citation count, across all pages."""
    papers = parse_works(first_dom)
    if not papers:
        return []
    cstart = 20
    while cstart < MAX_WORK_PAGES * 20:
        dom = dump_dom(chrome, "%s&cstart=%d" % (SCHOLAR_URL, cstart))
        batch = parse_works(dom)
        if not batch:
            break
        papers.extend(batch)
        if len(batch) < 20:
            break
        cstart += 20
    return papers


def norm_title(s):
    """Normalise a paper title so site titles can be matched to Scholar ones.

    Punctuation, dashes and quotes vary between the site, the journal and
    Scholar; folding them all away leaves just the words, which is what the
    comparison actually cares about.
    """
    s = (s or "").lower()
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s)
    s = re.sub(r"[\u2018\u2019\u02bc`\u00b4]", "'", s)
    s = re.sub(r"[\u201c\u201d]", '"', s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return s.strip()


# Words that carry no identifying weight in a paper title. Dropped before the
# fuzzy comparison so that "X during the Holocene" and "X in the Holocene" are
# recognised as the same paper.
STOPWORDS = set(
    """a an and are as at based by during for from in into is it its of on or
       the their to using was were with within new""".split()
)


def keywords(normalised):
    return {w for w in normalised.split() if len(w) > 2 and w not in STOPWORDS}


def dice(a, b):
    """Sørensen-Dice coefficient over two keyword sets."""
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


# A title only counts as a fuzzy match if it overlaps the Scholar title this much
# AND beats the runner-up by this margin. Both guards matter: the margin is what
# stops a paper being given the citation count of a genuinely different paper
# that happens to have a near-identical title.
FUZZY_MIN = 0.62
FUZZY_MARGIN = 0.10

# The margin is compared with a tolerance because the scores are floats. A pair
# scoring 1.000 against 0.900 has a real margin of exactly FUZZY_MARGIN, but in
# binary floating point it comes out as 0.09999999999999998 and a bare >= test
# rejects it. That silently dropped a genuine match once already.
EPSILON = 1e-9

QUERY_RE = re.compile(r'href="https://scholar\.google\.com/scholar\?q=([^"]+)"')


def read_site_queries():
    """Every "find this paper" query string on the site, in page order.

    These are the *raw* attribute values, kept verbatim. They become the keys of
    the citation map, so assets/metrics.js only has to slice the href and do a
    string comparison - it never normalises a title itself.
    """
    seen, out = set(), []
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".html") or name.startswith("_"):
            continue
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            for q in QUERY_RE.findall(fh.read()):
                if q not in seen:
                    seen.add(q)
                    out.append(q)
    return out


# Scholar often files a paper under a shorter title than the journal's - here
# the site carries "... on the global land monsoon system ..." while Scholar has
# "... on global land monsoon ...". Keyword overlap cannot bridge that safely on
# its own: adding "system" drags the margin over the runner-up down to 0.095,
# just under FUZZY_MARGIN, and the paper silently loses its count. These few are
# therefore pinned by hand.
#
#   (a fragment identifying the site entry, the Scholar title to read from)
#
# Keyed by fragment rather than by the whole title so that small edits to the
# site title do not silently break the pin.
TITLE_ALIASES = [
    ("global land monsoon system",
     "Differential vegetation feedback on global land monsoon during the Mid-Holocene and Last Interglacial"),
]


def match_citations(queries, papers):
    """Map site query string -> citation count, but only where that is safe.

    An exact match after normalisation is taken directly; likewise an entry
    listed in TITLE_ALIASES. Everything else is compared on keyword overlap; a
    fuzzy match is accepted only when it clears both FUZZY_MIN and FUZZY_MARGIN.
    Queries that match nothing are simply absent from the result, so the page
    shows no count for them rather than a wrong one.
    """
    exact, keyed = {}, []
    for p in papers:
        n = norm_title(p["title"])
        exact.setdefault(n, p["citations"])
        keyed.append((keywords(n), p["citations"]))

    out, fuzzy = {}, []
    for q in queries:
        n = norm_title(unquote_plus(q))
        if n in exact:
            out[q] = exact[n]
            continue

        # Hand-pinned: read the count straight off the named Scholar entry. If
        # that entry has gone, fall through to the fuzzy comparison rather than
        # dropping the paper.
        pinned = next((t for frag, t in TITLE_ALIASES if frag in n), None)
        if pinned:
            pn = norm_title(pinned)
            if pn in exact:
                out[q] = exact[pn]
                continue

        k = keywords(n)
        ranked = sorted(((dice(k, kk), c) for kk, c in keyed), reverse=True)
        if (
            ranked
            and ranked[0][0] >= FUZZY_MIN
            and ranked[0][0] - ranked[1][0] >= FUZZY_MARGIN - EPSILON
        ):
            out[q] = ranked[0][1]
            fuzzy.append((unquote_plus(q), ranked[0][0]))
    return out, fuzzy


def build_payload(metrics, papers, citations, query_count):
    now = datetime.datetime.now().astimezone()
    return {
        "source": "Google Scholar",
        "profile": PROFILE_URL,
        "updated": now.isoformat(timespec="seconds"),
        "updatedDisplay": now.strftime("%d %B %Y"),
        "scholar": metrics,
        "works": len(papers) or None,
        "papers": papers,
        # keyed by the literal ?q= value of each "find this paper" link
        "citations": citations,
        "citationMatches": {"matched": len(citations), "queries": query_count},
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


# Elements on the homepage that carry the number as static text as well as a
# data-metric hook. assets/metrics.js overwrites them on load; rewriting them
# here keeps the page correct for anyone reading it with JavaScript switched off,
# instead of leaving numbers from whenever the markup was last hand-edited.
NUMERIC_METRICS = ("citations", "citationsSince", "hIndex", "hIndexSince",
                   "i10Index", "i10IndexSince", "works")


def sync_fallbacks(payload):
    """Rewrite the hard-coded metric numbers in index.html to match the scrape."""
    path = os.path.join(ROOT, "index.html")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        html = original = fh.read()

    values = dict(payload["scholar"])
    values["works"] = payload.get("works")

    updated = 0
    for key in NUMERIC_METRICS:
        value = values.get(key)
        if not isinstance(value, int):
            continue
        text = "{:,}".format(value)
        pattern = re.compile(
            r'(<[a-z]+[^>]*\bdata-metric="%s"[^>]*>)([^<]*)(</[a-z]+>)' % re.escape(key)
        )

        def swap(match, text=text):
            nonlocal updated
            if match.group(2) != text:
                updated += 1
            return match.group(1) + text + match.group(3)

        html = pattern.sub(swap, html)

    if html != original:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    return updated


def summarise(payload):
    s = payload["scholar"]
    m = payload.get("citationMatches") or {}
    return (
        "citations %d (since %s) | h-index %d | i10-index %d | works %s "
        "(top cited: %s) | publication counts %s/%s"
        % (
            s["citations"], s["citationsSince"], s["hIndex"], s["i10Index"],
            payload["works"],
            max((p["citations"] for p in payload.get("papers") or []), default=0),
            m.get("matched", 0), m.get("queries", 0),
        )
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

    papers = collect_works(chrome, dom)
    queries = read_site_queries()
    citations, fuzzy = match_citations(queries, papers)
    payload = build_payload(metrics, papers, citations, len(queries))

    previous = read_previous()
    if (
        previous
        and previous.get("scholar") == payload["scholar"]
        and previous.get("papers") == payload["papers"]
        and previous.get("citations") == payload["citations"]
    ):
        # Numbers unchanged: only refresh the timestamp so "last checked" stays honest.
        changed = False
    else:
        changed = True

    say("Scraped: %s" % summarise(payload))
    for title, score in fuzzy:
        say("  fuzzy %.2f  %s" % (score, title[:88]))

    # A pin points at a Scholar title by name; if Scholar renames or drops the
    # entry the pin goes dead and the paper quietly falls back to fuzzy matching.
    scholar_titles = {norm_title(p["title"]) for p in papers}
    for _frag, target in TITLE_ALIASES:
        if norm_title(target) not in scholar_titles:
            say("  WARNING: pinned Scholar title not found: %s" % target[:88])
    unmatched = [q for q in queries if q not in citations]
    if unmatched:
        say("  no Scholar entry yet (%d):" % len(unmatched))
        for q in unmatched:
            say("    - %s" % unquote_plus(q)[:88])
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

    touched = sync_fallbacks(payload)
    if touched:
        say("Rewrote %d hard-coded fallback number(s) in index.html" % touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
