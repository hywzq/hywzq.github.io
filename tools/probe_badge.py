#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure where the injected "Cited N" chips actually land inside their card.

Absolute positioning is easy to get subtly wrong (wrong containing block,
margin pushing it off, media query flipping it back), so measure the rendered
geometry instead of trusting the screenshot.
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
  var out = [];
  var badges = document.querySelectorAll('.pub-cite');
  out.push('badge count = ' + badges.length);
  badges.forEach(function (b, i) {
    var art = b.closest('article');
    var rb = b.getBoundingClientRect();
    var ra = art ? art.getBoundingClientRect() : null;
    if (!ra) { out.push('#' + i + ' no article ancestor'); return; }

    /* the chip is drawn over the card's first line, so check it does not
       collide with whatever text is actually on that line */
    var lab = art.querySelector(':scope > .research-label, :scope > h3');
    var gap = 'n/a';
    if (lab) {
      /* getBoundingClientRect includes padding, so measure the text itself -
         that is what can actually run under the chip. */
      var r = document.createRange();
      r.selectNodeContents(lab);
      var rt = r.getBoundingClientRect();
      var cs = getComputedStyle(lab);
      var overlapY = rt.top < rb.bottom && rb.top < rt.bottom;
      gap = 'padR=' + Math.round(parseFloat(cs.paddingRight))
          + ' textGap=' + Math.round(rb.left - rt.right) + 'px'
          + ' align=' + cs.textAlign
          + (overlapY && rb.left < rt.right ? ' OVERLAP' : '');
      r.detach && r.detach();
    }
    out.push('#' + i
      + ' text="' + b.textContent.trim() + '"'
      + ' pos=' + getComputedStyle(b).position
      + ' size=' + Math.round(rb.width) + 'x' + Math.round(rb.height)
      + ' fromCardTop=' + Math.round(rb.top - ra.top)
      + ' fromCardRight=' + Math.round(ra.right - rb.right)
      + ' labelGap=' + gap);
  });
  var pre = document.createElement('pre');
  pre.id = 'PROBE-OUT';
  pre.textContent = 'PROBE>>>' + out.join(' | ') + '<<<PROBE';
  document.body.appendChild(pre);
});
</script>
"""


def main():
    page = sys.argv[1] if len(sys.argv) > 1 else "research-highlights.html"
    width = sys.argv[2] if len(sys.argv) > 2 else "1440"
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
             "--allow-file-access-from-files", "--virtual-time-budget=8000",
             "--window-size=" + width + ",2000",
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