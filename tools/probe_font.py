#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe computed font-family of the bold section titles, to find out why the
Education section (which uses .about-card h3) reads differently from the rest
(which use .compact-item strong)."""

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
    ['appointments strong',  '#appointments .compact-item strong'],
    ['honors strong',        '#honors .compact-item strong'],
    ['funding strong',       '#funding .compact-item strong'],
    ['education h3',         '#education .about-card h3'],
    ['education h3 en',      '#education .about-card h3 span.en'],
    ['service strong',       '#service .compact-item strong'],
    ['model-data strong',    '#model-data .compact-item strong'],
    ['about-page rule',      '.about-page'],
    ['page__content h3',     '.page__content h3']
  ];
  var out = [];
  sel.forEach(function (pair) {
    var el = document.querySelector(pair[1]);
    if (!el) { out.push(pair[0] + ' = MISSING'); return; }
    var cs = getComputedStyle(el);
    out.push(pair[0] + ' = ' + cs.fontFamily + ' | ' + cs.fontSize);
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
    html = html.replace("</body>", PROBE + "</body>")

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


if __name__ == "__main__":
    main()