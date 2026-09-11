#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe the *computed* font-size of key text on a page.

Chrome's --dump-dom prints the DOM after scripts run, so injecting a small
script that records getComputedStyle() values gives ground truth instead of
eyeballing a screenshot - and it is immune to Chrome's local-CSS caching.

This exists because CSS specificity on this site is easy to get wrong:
theme.css declares `.page__content p` and `.sidebar p` at (0,1,1), so a bare
`.section-lead` or `.about-sidebar-nav__title` (0,1,0) silently loses and the
declared font-size never reaches the screen. Always probe after touching type.

    python3 tools/probe_type.py                # index.html
    python3 tools/probe_type.py research.html
"""

import io
import os
import re
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PROBE = """
<script>
window.addEventListener('load', function () {
  var sel = [
    ['nav title',        '.about-sidebar-nav__title'],
    ['nav link',         '.about-sidebar-nav a'],
    ['section h2',       '#appointments h2'],
    ['section lead',     '#appointments .section-lead'],
    ['item strong',      '#appointments .compact-item strong'],
    ['item p',           '#appointments .compact-item p'],
    ['card h3',          '.about-card h3'],
    ['card p',           '.about-card p'],
    ['tag pill',         '.tag-row > span'],
    ['metric label',     '.scholar-metric div > span'],
    ['metric small',     '.scholar-metric small'],
    ['metric number',    '.scholar-metric strong']
  ];
  var out = [];
  sel.forEach(function (pair) {
    var el = document.querySelector(pair[1]);
    out.push(pair[0] + ' = ' + (el ? getComputedStyle(el).fontSize : 'MISSING'));
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

    # Strip main.js so the language toggle cannot re-render over the probe.
    html = re.sub(r'\s*<script src="assets/main\.js"></script>', "", html)
    html = html.replace("</body>", PROBE + "</body>")

    tmp = os.path.join(ROOT, "_probe_tmp.html")
    with io.open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)

    try:
        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--allow-file-access-from-files", "--virtual-time-budget=6000",
             "--dump-dom", "file://" + urllib.parse.quote(tmp)],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # Match the rendered <pre> element, not the literal marker inside the
    # injected <script> source (which --dump-dom also echoes back).
    m = re.search(r'<pre id="PROBE-OUT">(.*?)</pre>', proc.stdout, re.S)
    if not m:
        sys.exit("probe did not run; chrome stderr:\n" + proc.stderr[-2000:])

    text = m.group(1)
    text = re.sub(r"^PROBE>>>|<<<PROBE$", "", text.strip())
    for item in text.split(" | "):
        print("  " + item.strip())


if __name__ == "__main__":
    main()
