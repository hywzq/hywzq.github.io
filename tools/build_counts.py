#!/usr/bin/env python3
"""Write every derived number on the site from its single source.

    python3 tools/build_counts.py           rewrite the pages
    python3 tools/build_counts.py --check   report drift only, exit 1

The numbers are counted from the content by tools/site_facts.py and written to
two places:

  * assets/counts-data.js - read by assets/counts.js, which applies the values
    at runtime on every page; and
  * the [data-fact] elements in the HTML - which is what a reader sees with
    JavaScript off, and what the diff shows when a count changes.

Both come from the same run, so they cannot disagree. tools/check_site.py fails
if a page is committed without this having been run.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_facts as sf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["index.html", "publications.html", "research.html", "research-highlights.html"]
DATA_JS = os.path.join("assets", "counts-data.js")

# <span data-fact="key">value</span> - the value is plain text, no nested tags,
# so a tight pattern is enough and cannot swallow neighbouring markup.
ANCHOR_RE = re.compile(r'(<(\w+)\b[^>]*data-fact="([^"]+)"[^>]*>)([^<]*)(</\2>)')

HEADER = """/* =========================================================
   Site counts - GENERATED FILE, DO NOT EDIT
   ---------------------------------------------------------
   Written by tools/build_counts.py from the content itself.
   The same values are baked into the [data-fact] elements in
   the HTML, so this file only has to serve readers whose
   browser runs JavaScript.

   Edit the content, then run:  python3 tools/build_counts.py
   ========================================================= */
window.__SITE_COUNTS__ = %s;
"""


def build(root):
    """(facts, year facts, {page: new html}) for the current content."""
    facts, by_year = sf.compute(root)
    years = sf.year_facts(by_year)

    values = dict(facts)
    for year, y in years.items():
        values["year-%s-papers" % year] = y["papers"]
        # Only years whose journal list is folded into "and N more" carry this
        # key. A year that gains enough journals to need one is reported as an
        # unused fact, which is the signal to add the anchor to the block.
        if y["more"]:
            values["year-%s-more" % year] = y["more"]

    pages, problems = {}, []

    for name in PAGES:
        html = sf.read(root, name)

        def sub(m):
            key = m.group(3)
            if key not in values:
                problems.append("%s: no such fact %r" % (name, key))
                return m.group(0)
            return m.group(1) + str(values[key]) + m.group(5)

        pages[name] = ANCHOR_RE.sub(sub, html)

    # facts that nothing on the site shows - usually a typo in the HTML, or a
    # fact that was removed from the pages but left behind here
    used = set()
    for name in PAGES:
        used.update(re.findall(r'data-fact="([^"]+)"', sf.read(root, name)))
    for key in sorted(set(values) - used):
        problems.append("nothing on the site uses the fact %r" % key)

    return values, years, pages, problems


def data_js(values):
    return HEADER % json.dumps(values, indent=2, sort_keys=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 instead of writing")
    args = ap.parse_args()

    values, years, pages, problems = build(ROOT)

    changed = []
    for name, new in pages.items():
        if new != sf.read(ROOT, name):
            changed.append(name)

    js_path = os.path.join(ROOT, DATA_JS)
    old_js = ""
    if os.path.exists(js_path):
        with open(js_path, encoding="utf-8") as fh:
            old_js = fh.read()
    js_stale = old_js != data_js(values)

    if args.check:
        for name in changed:
            print("! %s is out of step with the content" % name)
        if js_stale:
            print("! %s is out of step with the content" % DATA_JS)
        for p in problems:
            print("! %s" % p)
        if changed or js_stale or problems:
            print("\nrun: python3 tools/build_counts.py")
            return 1
        print("counts are in step with the content")
        return 0

    for name in changed:
        with open(os.path.join(ROOT, name), "w", encoding="utf-8") as fh:
            fh.write(pages[name])
        print("updated %s" % name)
    if js_stale:
        with open(js_path, "w", encoding="utf-8") as fh:
            fh.write(data_js(values))
        print("updated %s" % DATA_JS)

    if not changed and not js_stale:
        print("nothing to do - counts already match the content")

    for p in problems:
        print("! %s" % p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
