#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe computed font-family across every heading and body element on a page.

Used to audit the two-font system (Helvetica for headings, Times New Roman for
body). Run with the page name as argv, e.g.:

    python3 tools/probe_fonts_all.py index.html
    python3 tools/probe_fonts_all.py publications.html
"""

import io
import os
import re
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (label, css selector). The label is printed first, so a long list is easy
# to scan. Order: headings first, then body text, so a mismatch jumps out.
SELECTORS = [
    # --- masthead ---
    ["masthead first link",  ".greedy-nav .visible-links li:first-child a"],
    ["masthead link",        ".greedy-nav .visible-links li:nth-child(2) a"],
    ["masthead lang link",   ".masthead__menu-item--lang a"],

    # --- sidebar identity ---
    ["author name",          ".sidebar .author__name"],
    ["author bio",           ".sidebar .author__bio"],
    ["author urls label",    ".author__urls-wrapper a"],

    # --- ABOUT ME section nav ---
    ["ABOUT ME title",       ".about-sidebar-nav__title"],
    ["ABOUT ME item",        ".about-sidebar-nav a"],

    # --- about page sections ---
    ["section h2",           "#appointments h2"],
    ["section lead",         "#appointments .section-lead"],
    ["item strong",          "#appointments .compact-item strong"],
    ["item p",               "#appointments .compact-item p"],
    ["card h3",              "#education .about-card h3"],
    ["card p",               "#education .about-card p"],
    ["scholar big number",   ".scholar-metric strong"],
    ["scholar label",        ".scholar-metric div > span"],
    ["scholar small",        ".scholar-metric small"],
    ["tag pill",             ".tag-row > span"],
    ["service strong",       "#service .compact-item strong"],
]

PROBE = """
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
"""


def main():
    page = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    src = os.path.join(ROOT, page)
    with io.open(src, encoding="utf-8") as fh:
        html = fh.read()
    html = re.sub(r'\s*<script src="assets/main\.js"></script>', "", html)
    html = html.replace("</body>", PROBE % json_dumps(SELECTORS) + "</body>")

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
        sys.exit("probe did not run; chrome stderr:\n" + proc.stderr[-2000:])
    text = re.sub(r"^PROBE>>>|<<<PROBE$", "", m.group(1).strip())
    for item in text.split(" | "):
        print("  " + item.strip())


def json_dumps(obj):
    # Minimal JSON serialiser so this works on the system python3 without
    # importing json (which is fine, but keeps the template literal clean).
    return __import__("json").dumps(obj)


if __name__ == "__main__":
    main()