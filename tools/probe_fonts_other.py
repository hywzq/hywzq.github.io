#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick font probe for publications / research / research-highlights.

Verifies the two-font system on the non-About pages: every heading is
Helvetica, every body line is Times New Roman.
"""

import io
import os
import re
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PAGES = {
    "publications.html": [
        ["hero h1",            ".publication-hero h1"],
        ["hero copy",          ".publication-hero-copy"],
        ["kicker",             ".publication-kicker"],
        ["section h2 (First)", "h2#first-and-corresponding-author"],
        ["section h2 (Under)", "details.publication-group summary"],
        ["section h2 (Climate)","h2#climate-modelling-and-paleoclimate"],
        ["section h2 (Ecology)","h2#ecology"],
        ["publication list li", "#first-and-corresponding-author li"],
        ["pub-note badge",     ".pub-note"],
        ["pub-cite badge",     ".pub-cite"],
        ["legend",             ".scholar-meta"],
    ],
    "research.html": [
        ["hero h1",            ".research-hero h1"],
        ["hero copy",          ".research-hero-copy"],
        ["kicker",             ".research-kicker"],
        ["direction-card h2",  ".direction-card h2"],
        ["direction-card p",   ".direction-card p"],
        ["research-section h2",".research-section h2"],
        ["research-section lead", ".research-section .section-lead"],
        ["method-panel h2",    ".method-panel h2"],
        ["method-panel p",     ".method-panel p"],
    ],
    "research-highlights.html": [
        ["studies h2",         "#studies-title"],
        ["resources h2",       "#resources-title"],
        ["about h2",           "#about-title"],
        ["research label",     ".research-label"],
        ["hub paragraph",      ".research-hub p"],
        ["hub summary",        ".research-hub .summary"],
        ["hub h3",             ".research-hub h3"],
    ],
}


def probe(page, selectors):
    src = os.path.join(ROOT, page)
    with io.open(src, encoding="utf-8") as fh:
        html = fh.read()
    html = re.sub(r'\s*<script src="assets/main\.js"></script>', "", html)

    script = """
<script>
window.addEventListener('load', function () {
  var sels = %s;
  var out = [];
  sels.forEach(function (pair) {
    var el = document.querySelector(pair[1]);
    if (!el) { out.push(pair[0] + ' = MISSING'); return; }
    out.push(pair[0] + ' = ' + getComputedStyle(el).fontFamily);
  });
  var pre = document.createElement('pre');
  pre.id = 'PROBE-OUT';
  pre.textContent = 'PROBE>>>' + out.join(' | ') + '<<<PROBE';
  document.body.appendChild(pre);
});
</script>
""" % __import__("json").dumps(selectors)

    html = html.replace("</body>", script + "</body>")
    tmp = os.path.join(ROOT, "_probe_tmp.html")
    with io.open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)
    try:
        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--allow-file-access-from-files", "--virtual-time-budget=6000",
             "--dump-dom", "file://" + urllib.parse.quote(tmp)],
            capture_output=True, text=True, timeout=120)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    m = re.search(r'<pre id="PROBE-OUT">(.*?)</pre>', proc.stdout, re.S)
    if not m:
        print("  probe failed:", proc.stderr[-500:])
        return
    text = re.sub(r"^PROBE>>>|<<<PROBE$", "", m.group(1).strip())
    for item in text.split(" | "):
        print("  " + item.strip())


for page, selectors in PAGES.items():
    print(f"\n=== {page} ===")
    probe(page, selectors)