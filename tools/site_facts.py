"""The single source of truth for every number shown on the site.

Nothing on the site should carry a hand-maintained copy of a number that can
be counted from the content. This module does the counting, and
tools/build_counts.py is the only thing that writes the results out - into
assets/counts-data.js for the runtime, and into the [data-fact] elements in
the HTML for readers without JavaScript.

The facts, and where each one comes from:

    journal-papers        every entry in the four publication groups
    first-author-papers   the entries in the first group
    in-progress-papers    entries whose pub-note is a status, not an annotation
    highly-cited-papers   entries whose pub-note says "Highly Cited Paper"
    cmip6-datasets        the ESGF DOI links in the Model Data section
    research-directions   the direction-N sections on the research page
    pub-year-first/last   the earliest and latest year in the publication list

Add a fact here, then anchor it in the HTML with data-fact="<key>", then run
tools/build_counts.py. tools/check_site.py fails if the two ever disagree.
"""

import os
import re

# The four publication groups, in page order. "Papers by Year" is a <details>
# block with its own <ul>, and is deliberately not one of them.
GROUPS = [
    "first-and-corresponding-author",
    "under-review-and-submitted",
    "climate-dynamics-earth-system-modelling-and-paleoclimate",
    "ecology",
]

# A paper is in progress when its note says so. Matched on the note text rather
# than on a class, because the same element also carries "In Chinese" and
# "Highly Cited Paper", which are annotations rather than statuses.
IN_PROGRESS_RE = re.compile(r"under review|submitted|in revising", re.I)

# The same pub-note element also carries this annotation, which is a count in
# its own right: it is shown as an ESI tile on three different pages.
HIGHLY_CITED_RE = re.compile(r"highly cited", re.I)

# How many journals are named per year before the list is folded into "and N
# more". The named ones are the first N in order of appearance.
NAMED_PER_YEAR = 4

_ENTITIES = (
    ("&ndash;", "-"), ("&mdash;", "-"), ("&nbsp;", " "),
    ("&amp;", "&"), ("&#8217;", "'"), ("\u2013", "-"), ("\u2014", "-"),
)


def read(root, name):
    with open(os.path.join(root, name), encoding="utf-8") as fh:
        return fh.read()


def plain(markup):
    """Tag-stripped, entity-decoded, whitespace-collapsed text."""
    text = re.sub(r"<[^>]+>", " ", markup)
    for a, b in _ENTITIES:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def group_items(pub):
    """{group id: [<li> ...]} for the four publication groups."""
    items = {}
    for gid in GROUPS:
        block = re.search(
            r'<h2 id="%s".*?</h2>(.*?)(?=<h2 id=|<details|</section>|\Z)' % re.escape(gid),
            pub, re.S,
        )
        items[gid] = re.findall(r"<li\b.*?</li>", block.group(1) if block else "", re.S)
    return items


def publications(root):
    """Publication counts, plus {year: [journal, ...]} for the year block."""
    pub = read(root, "publications.html")
    items = group_items(pub)

    total = sum(len(v) for v in items.values())
    in_progress = 0
    highly_cited = 0
    by_year = {}

    for gid in GROUPS:
        for li in items[gid]:
            note = re.search(r'<span class="pub-note"[^>]*>(.*?)</span>', li, re.S)
            if note:
                text = plain(note.group(1))
                if IN_PROGRESS_RE.search(text):
                    in_progress += 1
                if HIGHLY_CITED_RE.search(text):
                    highly_cited += 1

            em = re.search(r"<em[^>]*>(.*?)</em>", li, re.S)
            years = re.findall(r"\b((?:19|20)\d{2})\b", plain(li))
            if em and years:
                by_year.setdefault(years[-1], []).append(plain(em.group(1)))

    return {
        "journal-papers": total,
        "first-author-papers": len(items[GROUPS[0]]),
        "in-progress-papers": in_progress,
        "highly-cited-papers": highly_cited,
    }, by_year


def datasets(root):
    """CMIP6-PMIP4 datasets published on ESGF, counted from the DOIs."""
    index = read(root, "index.html")
    section = re.search(r'<section[^>]*id="model-data".*?</section>', index, re.S)
    if not section:
        return 0
    return len(re.findall(r'href="[^"]*ESGF/CMIP6', section.group(0)))


def directions(root):
    """Research directions, counted from the direction-N sections."""
    return len(re.findall(r'id="direction-\d+"', read(root, "research.html")))


def compute(root="."):
    """(facts, by_year). by_year is {year: [journal, ...]}, newest first."""
    facts, by_year = publications(root)
    facts["cmip6-datasets"] = datasets(root)
    facts["research-directions"] = directions(root)
    if by_year:
        facts["pub-year-first"] = min(by_year)
        facts["pub-year-last"] = max(by_year)
    return facts, by_year


def year_facts(by_year):
    """{year: {"papers": n, "journals": m, "more": m - named}} for the year block.

    "named" is however many <em> the block actually lists, so the derived
    "and N more" stays right even if a year names fewer than NAMED_PER_YEAR.
    """
    out = {}
    for year, journals in by_year.items():
        distinct = sorted(set(journals))
        named = min(len(distinct), NAMED_PER_YEAR)
        out[year] = {
            "papers": len(journals),
            "journals": len(distinct),
            "more": len(distinct) - named,
        }
    return out
