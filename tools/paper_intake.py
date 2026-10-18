#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Turn a paper title into a ready-to-paste publication entry.

The publication list cannot be generated from Google Scholar, but it can be
built from a better source: OpenAlex knows the full author names, so it can say
which "Wang Z." is the author of this site, and it carries the journal, volume
and pages. Crossref fills the gaps.

    python3 tools/paper_intake.py "Title of the paper"
    python3 tools/paper_intake.py --new          # every NEW work from sync_scholar
    python3 tools/paper_intake.py "Title" --json # machine-readable

For each title it prints the authoritative record, a suggested group and
research direction, and the exact <li> markup. Nothing is written: the group,
the status note and the equal-contribution marks are still a judgement call.

Everything here is looked up against ONE OpenAlex author id, so a paper by a
different Zhenqian Wang can never be picked up by mistake.
"""

import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import refresh_metrics as rm          # noqa: E402

AUTHOR_ID = "A5045769083"             # openalex.org/A5045769083 - Qinghai University
AUTHOR_URL = "https://openalex.org/" + AUTHOR_ID
MAILTO = "hywzq@foxmail.com"          # OpenAlex is friendlier with a contact address

WORKS_URL = ("https://api.openalex.org/works"
             "?filter=author.id:%s"
             "&per-page=200&sort=publication_date:desc&mailto=" + MAILTO)

CACHE = os.path.join(HERE, ".openalex-works.json")
CACHE_HOURS = 12

# Records that are not papers in their own right. Kept out of the matching pool
# so a peer-review report cannot shadow the article it reviews.
NOT_A_PAPER = {"peer-review", "supplementary-materials", "erratum", "paratext"}

# A repository copy of a paper that is also published under a real journal.
# OpenAlex sometimes files only the repository version, which would put "DiVA
# (Stockholm University)" where the journal name belongs.
REPOSITORY_HINT = re.compile(
    r"\b(DiVA|Zenodo|Research Square|SSRN|ESSOAr|EarthArXiv|bioRxiv|medRxiv|"
    r"Preprints?\.org|arXiv|Repository|Institutional Repository)\b", re.I)

TOP_JOURNALS = {
    "nature", "science", "nature climate change", "nature communications",
    "science advances", "proceedings of the national academy of sciences", "pnas",
}

# Words that carry no weight when guessing where an entry belongs. Matched
# against the title, so they are deliberately broad - this is a suggestion for
# a human to accept or overrule, not a classifier.
ECOLOGY_WORDS = set("""ecosystem ecosystems vegetation drought productivity carbon
    evapotranspiration aridity species biodiversity resilience soil moisture water
    efficiency npp gpp grassland forest biome leaf gross net primary greening
    dryland drylands land""".split())

CLIMATE_WORDS = set("""monsoon paleoclimate pliocene miocene holocene pleistocene
    interglacial glacial amoc enso jet westerlies westerly sea ice simulation model
    cmip pmip orbital topography teleconnection variability ocean atmosphere
    atmospheric african asian pacific atlantic arctic fire bvoc""".split())

DIRECTIONS = [
    ("direction-1", "Monsoon Dynamics and Variability",
     set("monsoon monsoons summer jet itcz boundary indian east asian".split())),
    ("direction-2", "Vegetation-Climate Feedbacks",
     set("vegetation feedback feedbacks bvoc greening fire land cover".split())),
    ("direction-3", "Paleoclimate Modelling and Model Development",
     set("""pliocene miocene holocene interglacial pleistocene paleoclimate
            simulation model pmip ec-earth deep time""".split())),
    ("direction-4", "Climate Variability and Teleconnections",
     set("""amoc enso teleconnection teleconnections variability westerlies
            sea ice arctic atlantic pacific multidecadal""".split())),
    ("direction-5", "Ecosystem Water and Carbon Responses",
     set("""evapotranspiration npp gpp productivity drought carbon water
            resilience aridity moisture efficiency""".split())),
]

# Journals whose names are written with deliberate lower case or in-joke
# capitalisation, which a title-caser would ruin.
KEEP_AS_IS = {"npj", "elife", "iscience", "msystems", "msphere", "mbio"}
SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
               "into", "of", "on", "or", "the", "to", "with", "vs", "versus"}

PARTICLES = {"de", "del", "der", "den", "da", "di", "la", "le", "van", "von", "bin", "al"}


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #

def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "site-tools/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.loads(fh.read().decode("utf-8"))


def author_works(refresh=False):
    """Every work OpenAlex attributes to this author, newest first."""
    if not refresh and os.path.exists(CACHE):
        age = (time.time() - os.path.getmtime(CACHE)) / 3600.0
        if age < CACHE_HOURS:
            try:
                with io.open(CACHE, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass
    works = []
    cursor = "*"
    while cursor:
        url = WORKS_URL % AUTHOR_ID
        if cursor != "*":
            url += "&cursor=" + urllib.parse.quote(cursor)
        try:
            page = get_json(url)
        except urllib.error.URLError as exc:
            if works:
                break
            raise SystemExit("OpenAlex unreachable: %s" % exc)
        works.extend(page.get("results", []))
        cursor = (page.get("meta") or {}).get("next_cursor")
        if len(works) >= (page.get("meta") or {}).get("count", 0):
            break
    with io.open(CACHE, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(works, ensure_ascii=False))
    return works


# --------------------------------------------------------------------------- #
# turning a work into the pieces the page needs
# --------------------------------------------------------------------------- #

def short_name(display):
    """'Zhenqian Wang' -> 'Wang Z.', 'Timo A. M. Pugh' -> 'Pugh T. A. M.'"""
    parts = [p for p in re.split(r"\s+", (display or "").strip()) if p]
    if not parts:
        return ""
    if not re.search(r"[A-Za-z]", display):
        return display.strip()          # a Chinese name: leave it alone
    surname = parts[-1]
    given = parts[:-1]
    if len(parts) > 1 and parts[-2].lower() in PARTICLES:
        surname = parts[-2] + " " + surname
        given = parts[:-2]
    initials = " ".join(p[0].upper() + "." for p in given if p[0].isalpha())
    return (surname + (" " + initials if initials else "")).strip()


def name_of(authorship):
    """The name to print for one author.

    OpenAlex sometimes stores a Chinese author under the Chinese form of the
    name while the raw record still has the Latin one, which is what the site
    uses ("Yang X.", not "杨小千").
    """
    display = (authorship.get("author") or {}).get("display_name") or ""
    if re.search(r"[A-Za-z]", display):
        return display
    return authorship.get("raw_author_name") or display


def journal_name(raw):
    """Fix the all-lower-case journal names OpenAlex sometimes returns."""
    if not raw:
        return ""
    words = raw.split()
    if any(re.search(r"[a-z][A-Z]", w) or re.match(r"^[A-Z]{2,}$", w)
           for w in words[1:]):
        return raw                     # deliberate capitalisation already
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in KEEP_AS_IS:
            out.append(w)
        elif i and low in SMALL_WORDS:
            out.append(low)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def pages(biblio):
    first = (biblio or {}).get("first_page")
    last = (biblio or {}).get("last_page")
    if not first:
        return ""
    if last and last != first:
        return "%s\u2013%s" % (first, last)
    return first


def record(work):
    """The bits of an OpenAlex work that the publication entry is built from."""
    authors = work.get("authorships") or []
    mine = [i for i, a in enumerate(authors)
            if (a.get("author") or {}).get("id") == AUTHOR_URL]
    source = ((work.get("primary_location") or {}).get("source") or {})
    biblio = work.get("biblio") or {}
    journal = journal_name(source.get("display_name") or "")
    names = [short_name(name_of(a)) for a in authors]
    return {
        "title": (work.get("title") or "").strip(),
        "authors": names,
        "bold_index": mine[0] if mine else None,
        "n_wang": sum(1 for n in names if n.startswith("Wang ")),
        "corresponding": bool(authors[mine[0]].get("is_corresponding")) if mine else False,
        "journal": journal,
        "year": work.get("publication_year"),
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "pages": pages(biblio),
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "type": work.get("type"),
        "cited_by": work.get("cited_by_count", 0),
        "is_top": journal.lower() in TOP_JOURNALS,
        "repository_source": bool(journal and REPOSITORY_HINT.search(journal)),
        "openalex": (work.get("id") or "").replace("https://openalex.org/", ""),
    }


def cite_tail(rec):
    """'2026, 419: 131153' - the bit between the journal name and the link."""
    year = str(rec["year"]) if rec["year"] else ""
    bits = ""
    if rec["volume"] and rec["issue"] and rec["pages"]:
        bits = "%s(%s): %s" % (rec["volume"], rec["issue"], rec["pages"])
    elif rec["volume"] and rec["pages"]:
        bits = "%s: %s" % (rec["volume"], rec["pages"])
    elif rec["volume"]:
        bits = str(rec["volume"])
    return ", ".join(x for x in (year, bits) if x)


def suggest_group(rec):
    """(group id, why). Group 1 is a role, group 2 a status, 3 and 4 topics."""
    if rec["bold_index"] == 0 or rec["corresponding"]:
        return "first-and-corresponding-author", (
            "you are the first author" if rec["bold_index"] == 0
            else "you are the corresponding author")
    if not rec["doi"] or rec["type"] in {"preprint", "conference-abstract"}:
        return "under-review-and-submitted", "no DOI yet"
    words = rm.keywords(rm.norm_title(rec["title"]))
    eco = len(words & ECOLOGY_WORDS)
    cli = len(words & CLIMATE_WORDS)
    if eco > cli:
        return "ecology", "%d ecology words vs %d climate words" % (eco, cli)
    return ("climate-dynamics-earth-system-modelling-and-paleoclimate",
            "%d climate words vs %d ecology words" % (cli, eco))


def suggest_directions(rec):
    words = rm.keywords(rm.norm_title(rec["title"]))
    scored = []
    for did, label, vocab in DIRECTIONS:
        hits = len(words & vocab)
        if hits:
            scored.append((hits, did, label))
    scored.sort(reverse=True)
    return [(did, label) for _, did, label in scored[:2]]


# --------------------------------------------------------------------------- #
# matching a title to a work
# --------------------------------------------------------------------------- #

def match(title, works):
    """(work, score, runner_up_score). Same fuzzy rule the site checker uses."""
    kw = rm.keywords(rm.norm_title(title))
    scored = []
    for w in works:
        if w.get("type") in NOT_A_PAPER:
            continue
        scored.append((rm.dice(kw, rm.keywords(rm.norm_title(w.get("title") or ""))), w))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return None, 0.0, 0.0
    top = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    return top[1], top[0], runner


def markup(rec, node_id):
    """The <li> line, with the bolded author and the Scholar lookup link."""
    names = []
    for i, name in enumerate(rec["authors"]):
        if i == rec["bold_index"]:
            names.append("<strong>%s</strong>%s" % (name, "*" if rec["corresponding"] else ""))
        else:
            names.append(name)
    journal = ('<em class="journal-top">%s</em>' % rec["journal"] if rec["is_top"]
               else "<em>%s</em>" % rec["journal"])
    q = urllib.parse.quote_plus(rec["title"])
    return ('<li data-page-node-id="%s">%s %s. %s, %s. '
            '<a href="https://scholar.google.com/scholar?q=%s" '
            'data-page-node-id="%s">Find it</a></li>'
            % (node_id, ", ".join(names), rec["title"], journal,
               cite_tail(rec) or str(rec["year"] or ""), q, new_node_id()))


def new_node_id():
    import base64
    import secrets
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")[:22]


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

def describe(title, works):
    work, score, runner = match(title, works)
    if not work or score < rm.FUZZY_MIN:
        return {"query": title, "match": None, "score": round(score, 3),
                "runner_up": round(runner, 3)}
    rec = record(work)
    group, why = suggest_group(rec)
    return {
        "query": title, "match": rec, "score": round(score, 3),
        "runner_up": round(runner, 3), "group": group, "group_reason": why,
        "directions": suggest_directions(rec),
        "markup": markup(rec, new_node_id()),
    }


def show(res):
    print("=" * 78)
    print("QUERY   %s" % res["query"])
    rec = res["match"]
    if not rec:
        print("MATCH   none  (best score %.2f, runner-up %.2f)"
              % (res["score"], res["runner_up"]))
        print("        Not on OpenAlex under this author id yet. Check by hand.")
        return
    print("MATCH   %.2f  (runner-up %.2f)  %s" % (res["score"], res["runner_up"], rec["openalex"]))
    print("TITLE   %s" % rec["title"])
    bold = rec["bold_index"]
    print("AUTHORS %s" % ", ".join(rec["authors"]))
    if bold is None:
        print("        !! you are not in this author list - wrong paper?")
    else:
        print("        bold = #%d  %s%s"
              % (bold + 1, rec["authors"][bold],
                 "  (corresponding)" if rec["corresponding"] else ""))
    if rec["n_wang"] > 1:
        print("        !! %d 'Wang Z.' in this list - register the bold index in"
              " WANG_BOLD, tools/check_site.py" % rec["n_wang"])
    print("JOURNAL %s%s" % (rec["journal"] or "(none)",
                            "   [top journal]" if rec["is_top"] else ""))
    if rec["repository_source"]:
        print("        !! OpenAlex filed this under a repository, not the journal")
    print("CITE    %s" % (cite_tail(rec) or "?"))
    print("DOI     %s" % (rec["doi"] or "(none - probably not published yet)"))
    print("TYPE    %s, %d citations" % (rec["type"], rec["cited_by"]))
    print("GROUP   %s   (%s)" % (res["group"], res["group_reason"]))
    if res["directions"]:
        print("CARD    %s" % ", ".join("%s %s" % d for d in res["directions"]))
    print("\n%s\n" % res["markup"])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    as_json = "--json" in sys.argv
    works = author_works(refresh="--refresh" in sys.argv)

    titles = list(args)
    if "--new" in sys.argv:
        import sync_scholar
        res = sync_scholar.compare()
        if not res:
            print("no assets/metrics.json - run tools/refresh_metrics.py first")
            return 2
        titles += [p["title"] for p, _, _ in res["new"]]
        if not res["new"]:
            print("nothing new on Scholar; nothing to look up")
            return 0

    if not titles:
        print(__doc__.strip())
        return 0

    out = [describe(t, works) for t in titles]
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for res in out:
            show(res)
        print("Check the group, add a status note if the paper is still in review,")
        print("then run: python3 tools/build_counts.py && python3 tools/check_site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
