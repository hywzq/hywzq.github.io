#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconcile the publication list against the Google Scholar profile.

Google Scholar cannot *be* the source of the publication list, but it is a very
good check on it. This tool reads the profile dump that refresh_metrics.py
already writes (assets/metrics.json), matches it against publications.html by
title, and prints the differences. It never edits anything.

    python3 tools/sync_scholar.py           # report
    python3 tools/sync_scholar.py --strict  # exit 1 if something needs a look
    python3 tools/sync_scholar.py --watch   # one line for the log, notify on change

Four things can come out of the comparison:

  RENAMED   a site title and a Scholar title overlap heavily but not fully.
            Usually a paper that was published under a different title than
            the preprint - the exact failure this tool exists to catch.
  RETITLED  the pair matched, but the wording is not identical. Most of these
            are harmless (Scholar writes "twenty-first" where the site writes
            "21st"); a few are real renames.
  NEW       a Scholar work with no counterpart on the site at all.
  UNINDEXED a published site entry Scholar does not list yet. Normal for
            anything from the last few months.
  (silent)  site entries carrying a status note ("Under review", "Submitted",
            "In revising"). Scholar only indexes published work, so these are
            expected to be absent and are not reported.

Why not generate the list from Scholar instead? See SCHOLAR.md.
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import refresh_metrics as rm          # noqa: E402
import site_facts as sf               # noqa: E402

METRICS = os.path.join(ROOT, "assets", "metrics.json")
PUBLICATIONS = os.path.join(ROOT, "publications.html")

# What the last unattended run already announced. Kept out of the repo: it is
# about this machine's notification history, not about the site.
STATE = os.path.join(HERE, ".scholar-state.json")

# A title pair scoring in this band is too different to be a match and too
# similar to be a coincidence - that is what a retitled paper looks like.
RENAME_MIN = 0.45

# Conference abstracts live on the Scholar profile and have no journal, so they
# would otherwise come back as "new paper" on every run. They are not journal
# papers and do not belong in the publication list. Keyed by the normalised
# title, so a slight rewording in Scholar will surface it again - which is the
# behaviour we want if one of them is ever published properly.
IGNORE = {
    "interactive versus inventory based bvoc emissions reshape regional cloud "
    "radiative and ozone feedbacks in ec earth3 aerchem bvoc",
    "monsoon trend and multi scale variability changes over the last 6000 years",
    "beyond constitutive plant bvocs modelling emissions from litter permafrost "
    "soil forest management and stress disturbance",
    "natural variability has dominated the movement of high asia polar jet over "
    "the past six centuries",
}

# The author list is "Surname I., Surname I. M., ..." and runs straight into the
# title, so the title starts after the last set of initials.
AUTHOR_TAIL = re.compile(r"[A-Z][A-Za-z\u2019'\-]+(?: [A-Z]\.)+")


def strip_authors(text):
    """Drop the author prefix from a rendered publication entry."""
    last = None
    for last in AUTHOR_TAIL.finditer(text):
        pass
    if not last:
        return text.strip()
    return text[last.end():].lstrip(".#, ").strip()


def site_entries():
    html = io.open(PUBLICATIONS, encoding="utf-8").read()
    items = sf.group_items(html)
    out = []
    for gid in sf.GROUPS:
        for li in items[gid]:
            em = re.search(r"<em[^>]*>.*?</em>", li, re.S)
            head = li[:em.start()] if em else li
            note = re.search(r'<span class="pub-note"[^>]*>(.*?)</span>', li, re.S)
            out.append({
                "group": gid,
                "title": strip_authors(sf.plain(re.sub(r"<[^>]+>", " ", head))),
                "note": sf.plain(note.group(1)) if note else "",
                "node": (re.search(r'data-page-node-id="([^"]+)"', li) or [None, ""])[1],
            })
    return out


def best(kw, pool):
    """(best object, score) for a keyword set against a pool of (object, set)."""
    top, score = None, 0.0
    for obj, other in pool:
        s = rm.dice(kw, other)
        if s > score:
            top, score = obj, s
    return top, score


def compare():
    """Match the site list against the Scholar profile. Reads, never writes."""
    if not os.path.exists(METRICS):
        return None

    payload = json.load(io.open(METRICS, encoding="utf-8"))
    scholar = payload.get("papers", [])
    site = site_entries()

    sch = [(p, rm.keywords(rm.norm_title(p["title"]))) for p in scholar]
    sit = [(s, rm.keywords(rm.norm_title(s["title"]))) for s in site]

    renamed, new, unindexed, retitled, ignored = [], [], [], [], []

    for s, kw in sit:
        if not kw:
            continue
        match, score = best(kw, sch)
        if score >= rm.FUZZY_MIN:
            # A 1.00 score means the keyword sets are identical, so any
            # difference is punctuation ("A.D." vs "AD") - not worth a look.
            if score < 0.999 and rm.norm_title(s["title"]) != rm.norm_title(match["title"]):
                retitled.append((s, match, score))
            continue
        if s["note"]:
            continue                      # expected to be absent from Scholar
        if score >= RENAME_MIN:
            renamed.append((s, match, score))
        else:
            unindexed.append((s, match, score))

    for p, kw in sch:
        match, score = best(kw, sit)
        if score >= RENAME_MIN:
            continue
        if rm.norm_title(p["title"]) in IGNORE:
            ignored.append(p)
        else:
            new.append((p, match, score))

    return {
        "scholar": sch, "site": sit,
        "renamed": renamed, "retitled": retitled,
        "new": new, "unindexed": unindexed, "ignored": ignored,
    }


def watch(res):
    """Announce a *change* in what needs a look, not the standing backlog.

    The 6-hourly job runs this every time it scrapes. Without the signature the
    same two unfixed entries would raise a notification four times a day, and a
    notification that fires when nothing changed is one you stop reading.
    """
    pending = (["RENAMED  " + s["title"][:80] for s, _, _ in res["renamed"]]
               + ["NEW      " + p["title"][:80] for p, _, _ in res["new"]])
    signature = hashlib.sha1("\n".join(sorted(pending)).encode("utf-8")).hexdigest()

    previous = {}
    if os.path.exists(STATE):
        try:
            previous = json.load(io.open(STATE, encoding="utf-8"))
        except Exception:
            previous = {}

    if not pending:
        if previous.get("pending"):
            print("WATCH nothing pending any more")
        with io.open(STATE, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"signature": "", "pending": 0}, indent=2))
        return 0

    print("WATCH %d item(s) need a look" % len(pending))
    for line in pending:
        print("  " + line)

    if signature == previous.get("signature"):
        print("WATCH unchanged since the last run; not notifying again")
        return 1

    body = "%d 条论文变化待处理：%s" % (len(pending), pending[0].split("  ", 1)[1][:60])
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "%s" with title "个人主页" subtitle "谷歌学术对账"'
             % body.replace("\\", "\\\\").replace('"', '\\"')],
            timeout=10, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("WATCH notification sent")
    except Exception as exc:                       # noqa: BLE001 - never fatal
        print("WATCH could not send a notification: %s" % exc)

    with io.open(STATE, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"signature": signature, "pending": len(pending),
                             "at": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2))
    return 1


def main():
    res = compare()
    if res is None:
        print("no %s - run tools/refresh_metrics.py first" % os.path.relpath(METRICS, ROOT))
        return 2

    renamed, retitled = res["renamed"], res["retitled"]
    new, unindexed, ignored = res["new"], res["unindexed"], res["ignored"]
    sch, sit = res["scholar"], res["site"]

    if "--watch" in sys.argv:
        # The unattended run: one line into the log, plus a notification when
        # the set of pending items changes. The full report below is only worth
        # printing when somebody is actually looking at it.
        return watch(res)

    print("%d works on Scholar, %d entries on the site" % (len(sch), len(sit)))
    print("%d site entries carry a status note and are skipped\n"
          % sum(1 for s in sit if s[0]["note"]))

    if renamed:
        print("RENAMED - no match, but a near neighbour on Scholar")
        for s, p, score in renamed:
            print("  %.2f  site:    %s" % (score, s["title"][:96]))
            print("        scholar: %s" % (p["title"] if p else "-")[:96])
            print("        [%s]" % s["node"])
        print()

    if retitled:
        print("RETITLED - matched, but the wording differs (check these by eye)")
        for s, p, score in retitled:
            print("  %.2f  site:    %s" % (score, s["title"][:96]))
            print("        scholar: %s" % p["title"][:96])
            print("        [%s]" % s["node"])
        print()

    if new:
        print("NEW - on Scholar, no entry on the site")
        for p, s, score in new:
            print("  %.2f  %s (%s, %s citations)"
                  % (score, p["title"][:88], p.get("year", "?"), p.get("citations", 0)))
        print()

    if ignored:
        print("IGNORED - conference abstracts, not journal papers")
        for p in ignored:
            print("        %s (%s)" % (p["title"][:88], p.get("year", "?")))
        print()

    if unindexed:
        print("UNINDEXED - on the site, not on Scholar yet")
        for s, p, score in unindexed:
            print("  %.2f  %s" % (score, s["title"][:96]))
            print("        [%s]" % s["node"])
        print()

    if not (renamed or retitled or new or unindexed):
        print("the list and the profile agree")

    if "--watch" in sys.argv:
        return watch(res)

    print("Nothing here is applied automatically: grouping, the bolded author and")
    print("the status notes all need a decision. Edit publications.html, then run")
    print("python3 tools/build_counts.py && python3 tools/check_site.py")

    if "--strict" in sys.argv and (renamed or new):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
