#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild assets/avatar.png from the original white-background studio photo.

Why this exists: the sidebar renders the photo inside a 140px circle, and the
framing has to be decided in the image itself. A tight 35x45mm ID crop puts the
head at ~100% of the circle, which reads as an oversized face; the brief is a
head-and-shoulders portrait where the shoulders and the top of the arms are
visible, matching the reference site this homepage is modelled on.

The head is located from the image (white background -> easy silhouette), so
nothing is hard-coded to one particular photo. Only two numbers describe the
look: FACE_SHARE (how much of the circle the head takes) and FACE_ANCHOR (where
the head sits vertically).

    python3 tools/make_avatar.py             # write assets/avatar.png
    python3 tools/make_avatar.py --dry-run   # print measurements, write nothing
    python3 tools/make_avatar.py --source /path/to/other.jpg

Needs Pillow. With the managed runtime:
    /Users/hywzq/.workbuddy-ai/binaries/python/envs/default/bin/python \
        tools/make_avatar.py
"""

import argparse
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = ("/Users/hywzq/Library/CloudStorage/OneDrive-Personal/"
       "申请相关/个人简历/证件照/白底.jpg")
OUT = os.path.join(ROOT, "assets", "avatar.png")

WHITE_CUTOFF = 242   # grayscale value below which a pixel counts as subject
HEAD_RATIO = 1.30    # head height / head width (ear to ear), anthropometric
HEAD_BAND = 0.45     # only look for the head in the top this share of the subject
FACE_SHARE = 0.40    # head height as a fraction of the square side
FACE_ANCHOR = 0.238  # head centre, as a fraction of the side, from the top
SIZE = 560           # final square avatar (4x the 140px display box)
WORK = 1600          # analyse at this longest edge; plenty for a 560px output


def measure(im):
    """Locate the head: hairline, chin line and horizontal centre.

    Detecting shoulders by looking for a sharp widening does NOT work here:
    in this photo the shoulder line slopes, so the width grows gradually and
    never jumps. Measuring the head's own width instead is both simpler and
    more reliable - the widest row in the upper part of the subject is the
    ear-to-ear line, and a head is ~1.30x as tall as it is wide.
    """
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    step = 2

    def span(y):
        xs = [x for x in range(0, w, step) if px[x, y] < WHITE_CUTOFF]
        return (xs[0], xs[-1]) if xs else None

    top = next((y for y in range(0, h, step) if span(y)), None)
    if top is None:
        raise SystemExit("ERROR: no subject found - is the background white?")
    bottom = next((y for y in range(h - 1, top, -step) if span(y)), top)

    # Widest row in the upper part of the subject = ear-to-ear line.
    limit = top + int((bottom - top) * HEAD_BAND)
    head_width = 0
    ear_y = top
    for y in range(top, max(limit, top + step), step):
        s = span(y)
        if s and (s[1] - s[0]) > head_width:
            head_width = s[1] - s[0]
            ear_y = y

    head_height = int(round(head_width * HEAD_RATIO))
    head_bottom = min(top + head_height, bottom)
    head_height = head_bottom - top

    xs = []
    for y in range(top, head_bottom + 1, step):
        s = span(y)
        if s:
            xs.append((s[0] + s[1]) / 2.0)
    cx = int(sum(xs) / len(xs)) if xs else w // 2

    return {
        "top": top,
        "bottom": bottom,
        "head_bottom": head_bottom,
        "head_width": head_width,
        "head_height": head_height,
        "ear_y": ear_y,
        "cx": cx,
    }


def build(im, m, dry=False):
    w, h = im.size
    side = int(round(m["head_height"] / FACE_SHARE))
    head_cy = m["top"] + m["head_height"] / 2.0
    x0 = int(round(m["cx"] - side / 2.0))
    y0 = int(round(head_cy - side * FACE_ANCHOR))

    print("source        : %dx%d (analysed at %dx%d)"
          % (im.size[0], im.size[1], w, h))
    print("hairline      : y=%d      chin/neck: y=%d" % (m["top"], m["head_bottom"]))
    print("head          : %d tall x %d wide, centre x=%d"
          % (m["head_height"], m["head_width"], m["cx"]))
    print("square side   : %d  -> head is %.0f%% of the circle"
          % (side, 100.0 * m["head_height"] / side))
    print("crop origin   : (%d, %d)   [negative = padded with white]" % (x0, y0))

    if dry:
        return None

    # Paste onto a white canvas with clipping, so out-of-bounds offsets are
    # safe and any missing area becomes white (matching the photo background).
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x0 + side), min(h, y0 + side)
    if sx1 > sx0 and sy1 > sy0:
        canvas.paste(im.crop((sx0, sy0, sx1, sy1)), (sx0 - x0, sy0 - y0))

    canvas.resize((SIZE, SIZE), Image.LANCZOS).save(OUT, "PNG", optimize=True)
    print("wrote         : %s (%d bytes)"
          % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT)))
    return OUT


def main():
    global FACE_SHARE, FACE_ANCHOR

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print measurements only")
    ap.add_argument("--source", default=SRC, help="path to the original photo")
    ap.add_argument("--face-share", type=float, default=FACE_SHARE,
                    help="head height as a fraction of the circle (default %.2f)" % FACE_SHARE)
    ap.add_argument("--face-anchor", type=float, default=FACE_ANCHOR,
                    help="head centre from the top, as a fraction (default %.3f)" % FACE_ANCHOR)
    args = ap.parse_args()

    FACE_SHARE, FACE_ANCHOR = args.face_share, args.face_anchor

    if not os.path.exists(args.source):
        raise SystemExit("ERROR: source photo not found: %s" % args.source)

    im = Image.open(args.source).convert("RGB")
    if max(im.size) > WORK:
        s = WORK / float(max(im.size))
        im = im.resize((int(im.size[0] * s), int(im.size[1] * s)), Image.LANCZOS)

    build(im, measure(im), dry=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
