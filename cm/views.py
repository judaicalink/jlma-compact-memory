"""The HTML views of the showcase. Each returns (status, html)."""

import json
import re

from . import config, solr
from . import search as S
from .data import CLASS_NAMES, life
from .html import bars, cm_iri, ep_iri, esc, fmt, iiif, page, pct, platform, sparql_link, u

JLP = "PREFIX jl: <http://data.judaicalink.org/ontology/>\n"


class NotFound(Exception):
    pass


# ---------------------------------------------------------------------------------------------------- pieces

def journal_title(D, jid):
    return D.journals.get(jid, {}).get("title") or f"Journal {jid}"


def ent_link(D, n, cls="cm-chip", extra=""):
    x = D.entities.get(int(n))
    if not x:
        return f'<span class="{cls}">ep/{esc(n)}</span>'
    return (f'<a class="{cls} cm-{esc(x["cls"])}" href="{u(f"/entity/{x["ep"]}")}" '
            f'title="{esc(CLASS_NAMES.get(x["cls"], ""))}{(" · " + esc(life(x))) if life(x) else ""}">'
            f'{esc(x["label"])}{extra}</a>')


def page_title(doc):
    bits = [doc.get("issue") or doc.get("volume") or ""]
    if doc.get("label"):
        bits.append(f"p. {doc['label']}")
    elif doc.get("seq"):
        bits.append(f"page {doc['seq']}")
    return " · ".join(b for b in bits if b)


def date_of(doc):
    d = doc.get("date", "")
    return d[:10] if d else ""


def breadcrumbs(D, nid, jid=None, here=None):
    ch = list(reversed(D.chain(nid))) if nid else []
    jid = jid or (D.nodes.get(nid, {}).get("j") if nid else None)
    items = [f'<a href="{u("/journals")}">Journals</a>']
    if jid:
        items.append(f'<a href="{u(f"/journal/{jid}")}">{esc(journal_title(D, jid))}</a>')
    for k, n in ch:
        items.append(f'<a href="{u(f"/issue/{k}")}">{esc(node_label(n))}</a>')
    if here:
        items.append(f"<span>{esc(here)}</span>")
    return '<nav class="cm-crumbs" aria-label="Breadcrumbs">' + " › ".join(items) + "</nav>"


def node_label(n):
    return n.get("l") or n.get("ty") or n.get("d") or n.get("t", "unit")


NODE_TYPES = {"volume": "Volume", "issue": "Issue", "article": "Article", "unit": "Unit"}


def result_item(D, doc, a, hl):
    vlid = doc["id"]
    jid = doc.get("journal")
    snip = ""
    if hl.get(vlid, {}).get("text"):
        snip = " … ".join(hl[vlid]["text"])
    elif "text" in doc:
        snip = S.mention_snippet(doc.get("text", ""), S.mentions_of(doc), set(a["e"]) | set(a["pl"]))
    ms = S.mentions_of(doc)
    counts = {}
    for m in ms:
        counts[m[0]] = counts.get(m[0], 0) + 1
    sel = {int(x) for x in a["e"] + a["pl"]}
    ents = sorted(counts, key=lambda n: (n not in sel, -counts[n]))[:6]
    chips = "".join(ent_link(D, n, "cm-chip" + (" on" if n in sel else "")) for n in ents)
    more = len(counts) - len(ents)
    link = u(f"/page/{vlid}", q=a["q"] or None, e=a["e"] + a["pl"])
    meta = " · ".join(esc(x) for x in (date_of(doc), page_title(doc)) if x)
    return f"""<li class="cm-hit">
<a class="cm-thumb" href="{link}"><img loading="lazy" src="{iiif(vlid)}" alt="" width="100" height="140"></a>
<div class="cm-hit-body">
<div class="cm-hit-head"><a href="{link}">{esc(journal_title(D, jid))}</a></div>
<div class="jl-meta">{meta}{(' · ' + esc(doc['article'][:120])) if doc.get('article') else ''}</div>
<p class="cm-snip">{snip}</p>
{f'<div class="cm-chips">{chips}{f"<span class=jl-meta>+{more}</span>" if more > 0 else ""}</div>' if chips else ''}
</div></li>"""


def pager(a, total, rows=S.ROWS, path="/search", extra=None):
    last = min((total + rows - 1) // rows, 500)
    if last <= 1:
        return ""
    p = a["p"]

    def link(n, t):
        params = dict(base_params(a), **(extra or {}))
        params["p"] = n if n > 1 else None
        return f'<a href="{u(path, **params)}">{t}</a>'
    out = []
    if p > 1:
        out.append(link(p - 1, "← Previous"))
    out.append(f"<span>Page {p} of {fmt(last)}</span>")
    if p < last:
        out.append(link(p + 1, "Next →"))
    return '<nav class="cm-pager" aria-label="Result pages">' + "".join(out) + "</nav>"


def base_params(a, **change):
    p = {"q": a["q"] or None, "e": a["e"], "occ": a["occ"], "bp": a["bp"], "pl": a["pl"], "cls": a["cls"],
         "j": a["j"], "lang": a["lang"], "pt": a["pt"], "from_": a["from"], "to": a["to"],
         "sort": a["sort"] if a["sort"] != ("rel" if a["q"] else "date") else None}
    p.update(change)
    return p


def toggle(a, key, value):
    """The search URL with value added to or removed from parameter key."""
    vals = list(a[key])
    vals = [v for v in vals if v != value] if value in vals else vals + [value]
    return u("/search", **base_params(a, **{key: vals}))


# ---------------------------------------------------------------------------------------------------- start

EXAMPLES = [
    ("Pages mentioning rabbis", {"occ": "Rabbi"}),
    ("Mentions of Theodor Herzl", {"e": "1007316"}),
    ("“Palästina” on pages that mention a person born in Vienna", {"q": "Palästina", "bp": "2761369"}),
    ("Rabbis and Breslau, 1880–1900", {"occ": "Rabbi", "pl": "1002369", "from_": 1880, "to": 1900}),
    ("“Hachschara” in the full text", {"q": "Hachschara"}),
    ("Moses Mendelssohn in the 19th century", {"e": "1006237", "from_": 1800, "to": 1899}),
]


def home(D):
    rep = D.report
    vers = D.versions.get("datasets", {})
    ds = "".join(f'<li><a href="{esc(platform(config.JL_DATA + "datasets/" + s))}">{esc(s)}</a> {esc(v)}</li>'
                 for s, v in vers.items() if s != "compact-memory-supp")
    ex = "".join(f'<li><a href="{u("/search", **p)}">{esc(t)}</a></li>' for t, p in EXAMPLES)
    n_ent = len(D.entities)
    cls = {}
    for x in D.entities.values():
        cls[x["cls"]] = cls.get(x["cls"], 0) + 1
    body = f"""
<section class="cm-hero">
<h1>Compact Memory</h1>
<p class="jl-lead">{fmt(rep.get("docs", 846500))} pages of {fmt(sum(1 for j in D.journals.values() if j.get("bundlePages")))}
Jewish periodicals from the German-speaking countries, 1768–1938 and later, digitised by the University Library
Frankfurt am Main. Search their full text, or find pages by the people and places they mention and by what the
JudaicaLink knowledge graph knows about them.</p>
<form class="cm-bigsearch" action="{u("/search")}" role="search">
<input type="search" name="q" placeholder="Words in the full text, e.g. Gemeindeblatt or &quot;jüdische Frauen&quot;" aria-label="Full-text search">
<button class="jl-button" type="submit">Search</button>
</form>
<div class="cm-entsearch" data-ac>
<label for="ac-home">Or find pages by an entity they mention:</label>
<input id="ac-home" type="search" placeholder="A person, place or subject, e.g. Herzl, Breslau" autocomplete="off" data-ac-input data-ac-go="entity">
<ul class="cm-ac-list" data-ac-list hidden></ul>
</div>
</section>
<div class="cm-grid2">
<section><h2>Try</h2><ul class="cm-examples">{ex}</ul></section>
<section><h2>Explore</h2>
<ul class="jl-cards cm-entry">
<li><h3><a href="{u("/journals")}">Journals</a></h3><p>All {fmt(len(D.journals))} periodicals: title, place, period, pages per year, OCR quality, volumes and issues.</p></li>
<li><h3><a href="{u("/dashboard/")}">Dashboard</a></h3><p>The collection in figures: pages over time, languages, OCR quality, data issues, and how it links into the knowledge graph.</p></li>
</ul></section>
</div>
<section><h2>How the semantic search works</h2>
<p>In 2021, TagMe found {fmt(rep.get("stats", {}).get("exact", 0) + rep.get("stats", {}).get("moved", 0) + rep.get("stats", {}).get("not_found", 0)) or "749,446"}
mentions of {fmt(n_ent)} entities on 316,000 pages (dataset <a href="{esc(platform(config.JL_DATA + "datasets/cm-tagme"))}">cm-tagme</a>).
Each entity is represented by one JudaicaLink entity page ({fmt(cls.get("person", 0))} persons, {fmt(cls.get("place", 0))} places,
{fmt(cls.get("subject", 0))} subjects), which brings together what the datasets of JudaicaLink say about it: life dates, occupations, birth places,
links to the GND, VIAF and Wikidata. The index of this showcase stores, for every page, the entities it mentions and these facts about them,
so pages can be found by “mentions a person with occupation …” or “mentions a person born in …”, combined with words of the full text.
No machine learning: just the graph. Mentions were found automatically and are not checked; some are wrong.</p>
</section>
<section class="jl-note cm-versions"><h2>Data</h2>
<p>Full text: bundle <code>{esc(rep.get("bundle", config.BUNDLE))}</code> (the same texts as the search of the FID portal), indexed {esc(rep.get("built", "")[:10])}.
Graph data, versions loaded on this platform:</p><ul>{ds}</ul>
<p>Page images and the page viewer: <a href="https://sammlungen.ub.uni-frankfurt.de/cm">Visual Library of the UB Frankfurt</a> (IIIF).
The production full-text search of Compact Memory is in the portal of the <a href="{config.PRODUCTION}">FID Jewish Studies</a>.</p>
</section>"""
    return 200, page("", body, active="/")


# ---------------------------------------------------------------------------------------------------- search

def facet_block(title, items, key, a, label=lambda v: v, more=None, open_=True):
    if not items:
        return ""
    lis = []
    for v, c in items:
        on = v in a[key]
        lis.append(f'<li><a href="{esc(toggle(a, key, v))}"{" class=on aria-current=true" if on else ""}>'
                   f'<span>{esc(label(v))}</span><span class="cm-n">{fmt(c)}</span></a></li>')
    m = f'<li class="cm-more"><a href="{esc(more)}">more…</a></li>' if more else ""
    return (f'<details class="cm-facet"{" open" if open_ else ""}><summary>{esc(title)}</summary>'
            f'<ul>{"".join(lis)}{m}</ul></details>')


def search_view(D, params):
    a = S.clean(params)
    if not S.active(a):
        return 200, page("Search", search_form(D, a) + '<p class="jl-meta">Type words of the full text, pick an '
                         'entity, or start from one of the <a href="' + u("/") + '">examples</a>.</p>', active="/search",
                         wide=True)
    lim = {}
    if a["all"] in ("j", "occ", "bp", "pl"):
        lim[a["all"]] = 400
    try:
        res = S.query(a, facet_limit=lim)
    except solr.SolrError as e:
        return 400, page("Search", search_form(D, a) + f'<p class="jl-note">The query could not be run: {esc(e)}</p>',
                         active="/search", wide=True)
    total = res["response"]["numFound"]
    hl = res.get("highlighting", {})
    docs = res["response"]["docs"]
    F = lambda n: S.facet(res, n)
    more = lambda k: u("/search", **base_params(a), all=k)
    side = "".join([
        facet_block("Journal", F("journal"), "j", a, lambda v: journal_title(D, v),
                    more=None if a["all"] == "j" or len(F("journal")) < 12 else more("j")),
        facet_block("Language", F("lang"), "lang", a),
        facet_block("Unit the page belongs to", F("ptype"), "pt", a, open_=False),
        facet_block("Mentions a …", F("eclass"), "cls", a, lambda v: CLASS_NAMES.get(v, v)),
        facet_block("… person with occupation", F("occ"), "occ", a,
                    more=None if a["all"] == "occ" or len(F("occ")) < 12 else more("occ")),
        facet_block("… person born in", F("bplace"), "bp", a, D.place_name,
                    more=None if a["all"] == "bp" or len(F("bplace")) < 12 else more("bp")),
        facet_block("… place", F("ep_place"), "pl", a, lambda v: D.entities.get(int(v), {}).get("label", v),
                    more=None if a["all"] == "pl" or len(F("ep_place")) < 12 else more("pl")),
    ])
    years = [(int(y), c) for y, c in F("year")]
    yr_href = lambda y: u("/search", **base_params(a, from_=y, to=y))
    top_ents = [(int(v), c) for v, c in F("ep") if v not in a["e"]][:14]
    ents = "".join(f'<a class="cm-chip cm-{esc(D.entities.get(n, {}).get("cls", ""))}" href="{esc(toggle(a, "e", str(n)))}" '
                   f'title="Add as a filter">{esc(D.entities.get(n, {}).get("label", n))} <span class="cm-n">{fmt(c)}</span></a>'
                   for n, c in top_ents if n in D.entities)
    sorts = " · ".join(
        (f"<strong>{t}</strong>" if a["sort"] == k else f'<a href="{u("/search", **base_params(a, sort=k))}">{t}</a>')
        for k, t in (("rel", "relevance"), ("date", "oldest first"), ("-date", "newest first"))
        if k != "rel" or a["q"])
    items = "".join(result_item(D, d, a, hl) for d in docs)
    body = f"""{search_form(D, a)}
<div class="cm-results">
<aside class="cm-side" aria-label="Filters">{side}</aside>
<div class="cm-list">
<div class="cm-count"><strong>{fmt(total)}</strong> pages{f" · page {a['p']}" if a['p'] > 1 else ""}<span class="cm-sort">Sort: {sorts}</span></div>
{f'<div class="cm-yearchart"><div class="jl-meta">Pages per year (click a year to narrow down)</div>{bars(years, href=yr_href)}</div>' if len(years) > 1 else ''}
{f'<div class="cm-cooc"><span class="jl-meta">Most mentioned on these pages:</span> {ents}</div>' if ents else ''}
<ol class="cm-hits" start="{(a['p'] - 1) * S.ROWS + 1}">{items}</ol>
{'' if docs else '<p>No pages found. Remove a filter or try other words.</p>'}
{pager(a, total)}
</div></div>"""
    title = a["q"] or ", ".join(D.entities.get(int(n), {}).get("label", n) for n in a["e"]) or "Search"
    return 200, page(title, body, active="/search", q=a["q"], wide=True)


def search_form(D, a):
    chips = []
    for k, lab in (("e", lambda v: D.entities.get(int(v), {}).get("label", v)),
                   ("pl", lambda v: "place: " + D.entities.get(int(v), {}).get("label", v)),
                   ("occ", lambda v: "occupation: " + v), ("bp", lambda v: "born in: " + D.place_name(v)),
                   ("cls", lambda v: "mentions a " + CLASS_NAMES.get(v, v).lower()),
                   ("j", lambda v: journal_title(D, v)), ("lang", str), ("pt", str)):
        for v in a[k]:
            chips.append(f'<a class="cm-filter" href="{esc(toggle(a, k, v))}" title="Remove this filter">'
                         f'{esc(lab(v))} <span aria-hidden="true">×</span></a>')
    if a["from"] or a["to"]:
        chips.append(f'<a class="cm-filter" href="{u("/search", **base_params(a, from_=None, to=None))}">'
                     f'{a["from"] or "…"}–{a["to"] or "…"} <span aria-hidden="true">×</span></a>')
    hidden = "".join(f'<input type="hidden" name="{k}" value="{esc(v)}">'
                     for k in ("e", "pl", "occ", "bp", "cls", "j", "lang", "pt") for v in a[k])
    return f"""<form class="cm-form" action="{u("/search")}" role="search">
<div class="cm-form-row">
<input type="search" name="q" value="{esc(a["q"])}" placeholder="Words in the full text" aria-label="Full-text search">
<span class="cm-years"><input type="number" name="from" min="1700" max="2030" value="{a["from"] or ""}" placeholder="from" aria-label="From year">–<input type="number" name="to" min="1700" max="2030" value="{a["to"] or ""}" placeholder="to" aria-label="To year"></span>
<button class="jl-button" type="submit">Search</button>
</div>
<div class="cm-form-row cm-entsearch" data-ac>
<input type="search" placeholder="Add an entity: a person, place or subject the page mentions" autocomplete="off" aria-label="Add an entity" data-ac-input data-ac-go="filter">
<ul class="cm-ac-list" data-ac-list hidden></ul>
</div>
{hidden}
{f'<div class="cm-filters">{"".join(chips)}</div>' if chips else ''}
</form>"""


# ---------------------------------------------------------------------------------------------------- entity

def entity_view(D, n):
    x = D.entities.get(n)
    if not x:
        raise NotFound
    fq = f"ep:{solr.quote(n)}"
    res = solr.select(config.CORE, {
        "q": "*:*", "fq": fq, "rows": 8, "sort": "date asc,id asc",
        "fl": "id,journal,volume,issue,article,date,label,seq,mentions,text",
        "facet": "true", "facet.mincount": 1, "facet.field": ["year", "journal", "ep"],
        "f.year.facet.limit": -1, "f.year.facet.sort": "index", "f.journal.facet.limit": 10, "f.ep.facet.limit": 25})
    total = res["response"]["numFound"]
    years = [(int(y), c) for y, c in S.facet(res, "year")]
    journals = S.facet(res, "journal")
    co = [(int(v), c) for v, c in S.facet(res, "ep") if int(v) != n][:24]
    facts = []
    if x.get("born") or x.get("died"):
        facts.append(("Life", life(x)))
    if x.get("bplace"):
        bp = x["bplace"]
        name = D.place_name(bp["gid"]) if bp.get("gid") else bp.get("name")
        link = u("/search", bp=bp["gid"]) if bp.get("gid") else None
        facts.append(("Born in", f'{esc(name)}' + (f' · <a href="{link}">pages mentioning people born there</a>'
                                                   if link else ""), True))
    if x.get("dplace") and x["dplace"].get("name"):
        facts.append(("Died in", x["dplace"]["name"]))
    if x.get("occ"):
        facts.append(("Occupation", ", ".join(f'<a href="{u("/search", occ=o)}">{esc(o)}</a>' for o in x["occ"]), True))
    ids = x.get("ids", {})
    ext = []
    if "gnd" in ids:
        ext.append(f'<a href="https://d-nb.info/gnd/{esc(ids["gnd"])}">GND {esc(ids["gnd"])}</a>')
    if "viaf" in ids:
        ext.append(f'<a href="https://viaf.org/viaf/{esc(ids["viaf"])}">VIAF</a>')
    if "wikidata" in ids:
        ext.append(f'<a href="https://www.wikidata.org/wiki/{esc(ids["wikidata"])}">Wikidata {esc(ids["wikidata"])}</a>')
    if "geonames" in ids:
        ext.append(f'<a href="https://www.geonames.org/{esc(ids["geonames"])}">GeoNames</a>')
    if x.get("wikipedia"):
        ext.append(f'<a href="{esc(x["wikipedia"])}">Wikipedia</a>')
    if ext:
        facts.append(("Elsewhere", " · ".join(ext), True))
    if x.get("point"):
        lon, lat = x["point"]
        facts.append(("Coordinates", f'<a href="https://www.openstreetmap.org/?mlat={lat}&amp;mlon={lon}#map=8/{lat}/{lon}">'
                                     f'{lat:.3f}, {lon:.3f}</a>', True))
    facts.append(("In JudaicaLink", f'<a href="{esc(platform(ep_iri(n)))}">entity page ep/{n}</a> · TagMe '
                  + ", ".join(f'<a href="{esc(platform(config.JL_DATA + "data/dbpedia/" + t))}">dbpedia/{esc(t)}</a>'
                              for t in x["tagme"]), True))
    pr = x.get("presence", {})
    q_presence = (JLP + "SELECT ?mentions ?pages ?journals ?first ?last WHERE {\n"
                  f"  ?p jl:entity <{config.JL_DATA}data/dbpedia/{x['tagme'][0]}> ;\n"
                  "     jl:mentionCount ?mentions ; jl:pageCount ?pages ; jl:journalCount ?journals ;\n"
                  "     jl:firstMentionYear ?first ; jl:lastMentionYear ?last .\n}")
    presence = ""
    if pr:
        presence = (f'<p class="cm-presence">{fmt(pr.get("mentionCount", 0))} mentions on {fmt(pr.get("pageCount", 0))} pages '
                    f'of {fmt(pr.get("journalCount", 0))} journals, {esc(pr.get("firstMentionYear", ""))}–'
                    f'{esc(pr.get("lastMentionYear", ""))} {sparql_link(q_presence)}</p>')
    dl = "".join(f"<dt>{esc(f[0])}</dt><dd>{f[1] if len(f) > 2 else esc(f[1])}</dd>" for f in facts)
    jl = "".join(f'<li><a href="{u("/search", e=n, j=j)}">{esc(journal_title(D, j))}</a> <span class="cm-n">{fmt(c)}</span></li>'
                 for j, c in journals)
    cos = "".join(f'<a class="cm-chip cm-{esc(D.entities[m]["cls"])}" href="{u(f"/entity/{m}")}">{esc(D.entities[m]["label"])} '
                  f'<span class="cm-n">{fmt(c)}</span></a>' for m, c in co if m in D.entities)
    a = S.clean({"e": [str(n)]})
    items = "".join(result_item(D, d, a, {}) for d in res["response"]["docs"])
    alt = [v for v in x.get("alt", []) if v != x["pref"]][:8]
    body = f"""<nav class="cm-crumbs"><a href="{u("/search")}">Search</a> › entity</nav>
<header class="cm-enthead">
<span class="cm-kind cm-{esc(x["cls"])}">{esc(CLASS_NAMES.get(x["cls"], x["cls"]))}</span>
<h1>{esc(x["label"])}</h1>
{f'<p class="jl-meta">Also: {esc(" · ".join(alt))}</p>' if alt else ''}
{f'<p class="cm-abstract">{esc(x["abstract"])}</p>' if x.get("abstract") else ''}
</header>
<dl class="jl-facts">{dl}</dl>
<section><h2>In Compact Memory</h2>{presence}
<p><a class="jl-button" href="{u("/search", e=n)}">All {fmt(total)} pages mentioning {esc(x["label"])}</a></p>
<h3>Pages per year</h3>{bars(years, href=lambda y: u("/search", e=n, from_=y, to=y))}
</section>
<div class="cm-grid2">
<section><h3>Journals</h3><ul class="cm-plain">{jl}</ul></section>
<section><h3>Mentioned on the same pages</h3><div class="cm-chips">{cos or '<span class="jl-meta">none</span>'}</div>
<p class="jl-meta">Click one to see its view; to search pages mentioning both, <a href="{u("/search", e=n)}">add it as a filter in the search</a>.</p></section>
</div>
<section><h2>Earliest pages</h2><ol class="cm-hits">{items}</ol>
<p><a href="{u("/search", e=n, sort="-date")}">Latest pages</a> · <a href="{u("/search", e=n)}">all pages</a></p></section>
<p class="jl-meta">Mentions were found automatically by TagMe (2021) and are not checked. The facts come from the
JudaicaLink entity page and the datasets it brings together.</p>"""
    return 200, page(x["label"], body, wide=False)


# ---------------------------------------------------------------------------------------------------- page

def page_view(D, vlid, params):
    res = solr.select(config.CORE, {"q": f"id:{solr.quote(vlid)}", "fl": "*", "rows": 1})
    if not res["response"]["docs"]:
        raise NotFound
    doc = res["response"]["docs"][0]
    text = doc.get("text", "")
    q = (params.get("q") or [""])[0][:500]
    sel = {int(x) for x in params.get("e", []) if x.isdigit()}
    hits = []
    if q:
        try:
            h = solr.select(config.CORE, {
                "q": q, "defType": "edismax", "qf": "text", "q.op": "AND", "fq": f"id:{solr.quote(vlid)}", "fl": "id",
                "hl": "true", "hl.method": "unified", "hl.fl": "text", "hl.fragsize": 0, "hl.snippets": 1,
                "hl.tag.pre": "\x01", "hl.tag.post": "\x02", "hl.maxAnalyzedChars": 200000,
                "hl.defaultSummary": "false"})
            marked = (h.get("highlighting", {}).get(vlid, {}).get("text") or [""])[0]
            pos = 0
            for part in re.finditer(r"\x01(.*?)\x02", marked, re.S):
                start = part.start() - 2 * len(hits)
                hits.append((start, start + len(part.group(1))))
                pos = part.end()
        except solr.SolrError:
            hits = []
    ms = S.mentions_of(doc)
    spans = [(s, e, "q", None) for s, e in hits]
    spans += [(m[1], m[2], "e", m[0]) for m in ms if m[1] >= 0]
    spans.sort(key=lambda s: (s[0], s[2] != "e"))
    out, cur = [], 0
    for s, e, kind, n in spans:
        if s < cur:
            continue
        out.append(esc(text[cur:s]))
        frag = esc(text[s:e])
        if kind == "e":
            x = D.entities.get(n, {})
            cls = "cm-ent" + (" on" if n in sel else "") + f" cm-{x.get('cls', '')}"
            # a query hit inside the mention is marked as well
            if any(hs < e and he > s for hs, he in hits):
                frag = f"<mark>{frag}</mark>"
            out.append(f'<a class="{cls}" id="m{n}" href="{u(f"/entity/{n}")}" title="{esc(x.get("label", ""))}">{frag}</a>')
        else:
            out.append(f"<mark>{frag}</mark>")
        cur = e
    out.append(esc(text[cur:]))
    counts = {}
    for m in ms:
        counts[m[0]] = counts.get(m[0], 0) + 1
    ent_rows = "".join(
        f'<li>{ent_link(D, n, "cm-chip" + (" on" if n in sel else ""))} <span class="cm-n">{c}×</span> '
        f'<a class="cm-small" href="{esc(platform(ep_iri(n)))}" title="The entity page on the platform">ep/{n}</a></li>'
        for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], D.entities.get(kv[0], {}).get("label", ""))))
    unplaced = sum(1 for m in ms if m[1] < 0)
    # neighbours in the same unit
    prev = nxt = None
    pos_in = None
    if doc.get("parent"):
        sib = solr.select(config.CORE, {"q": "*:*", "fq": f"parent:{solr.quote(doc['parent'])}", "fl": "id,seq,label",
                                        "sort": "seq asc,id asc", "rows": 3000})["response"]["docs"]
        ids = [s["id"] for s in sib]
        if vlid in ids:
            i = ids.index(vlid)
            pos_in = (i + 1, len(ids))
            prev = sib[i - 1] if i > 0 else None
            nxt = sib[i + 1] if i + 1 < len(ids) else None
    keep = {"q": q or None, "e": [str(x) for x in sel]}
    nav = '<nav class="cm-pagenav">'
    nav += (f'<a href="{u(f"/page/{prev["id"]}", **keep)}" rel="prev">← {esc(prev.get("label") or "previous")}</a>'
            if prev else "<span></span>")
    if pos_in:
        nav += (f'<a href="{u(f"/issue/{doc["parent"]}")}">page {pos_in[0]} of {pos_in[1]} in this '
                f'{esc(NODE_TYPES.get(D.nodes.get(doc["parent"], {}).get("t"), "unit").lower())}</a>')
    nav += (f'<a href="{u(f"/page/{nxt["id"]}", **keep)}" rel="next">{esc(nxt.get("label") or "next")} →</a>'
            if nxt else "<span></span>")
    nav += "</nav>"
    jid = doc.get("journal")
    facts = [("Journal", f'<a href="{u(f"/journal/{jid}")}">{esc(journal_title(D, jid))}</a>', True)]
    for k, t in (("volume", "Volume"), ("issue", "Issue"), ("article", "Article")):
        if doc.get(k):
            facts.append((t, doc[k]))
    if doc.get("date"):
        facts.append(("Date", date_of(doc)))
    facts.append(("Page", (doc.get("label") or "–") + (f" (sequence {doc['seq']})" if doc.get("seq") else "")))
    if doc.get("lang"):
        facts.append(("Language", ", ".join(doc["lang"])))
    if doc.get("ptype"):
        facts.append(("Belongs to", doc["ptype"]))
    if doc.get("ocr") is not None:
        qo = (JLP + f"SELECT ?share WHERE {{ <{cm_iri(doc.get('iri', ''))}> jl:ocrKnownWordShare ?share }}")
        facts.append(("OCR quality", f'{pct(doc["ocr"])} known words {sparql_link(qo)}', True))
    if doc.get("iri"):
        facts.append(("IRI", f'<a href="{esc(platform(cm_iri(doc["iri"])))}"><code>…/{esc(doc["iri"])}</code></a>', True))
    facts.append(("Visual Library", f'<a href="{esc(config.UB_PAGE.format(vlid=vlid))}">page viewer of the UB Frankfurt</a>', True))
    dl = "".join(f"<dt>{esc(f[0])}</dt><dd>{f[1] if len(f) > 2 else esc(f[1])}</dd>" for f in facts)
    legend = []
    if hits:
        legend.append(f'<mark>{len(hits)} hits</mark> for “{esc(q)}”')
    if ms:
        legend.append(f'<span class="cm-ent">{len(ms) - unplaced} entity mentions</span>'
                      + (f" ({unplaced} not found in this text)" if unplaced else ""))
    body = f"""{breadcrumbs(D, doc.get("parent"), jid, here=doc.get("label") or f"page {doc.get('seq', '')}")}
<h1 class="cm-pagetitle">{esc(journal_title(D, jid))}<span class="jl-meta"> · {esc(" · ".join(x for x in (date_of(doc), page_title(doc)) if x))}</span></h1>
{nav}
<div class="cm-pageview">
<figure class="cm-scan"><a href="{esc(config.UB_PAGE.format(vlid=vlid))}" title="Open in the viewer of the UB Frankfurt">
<img src="{iiif(vlid, 1000)}" alt="Scan of the page" loading="lazy"></a>
<figcaption class="jl-meta">Image: UB Frankfurt, Visual Library (IIIF)</figcaption></figure>
<div class="cm-pageinfo">
<dl class="jl-facts">{dl}</dl>
{f'<h2>Mentioned entities</h2><ul class="cm-ents">{ent_rows}</ul>' if ent_rows else '<p class="jl-meta">No entity mentions on this page.</p>'}
</div></div>
<section class="cm-ocrsec"><h2>OCR text</h2>
{f'<p class="jl-meta cm-legend">{" · ".join(legend)}</p>' if legend else ''}
<div class="cm-ocr" lang="{'de' if 'German' in doc.get('lang', ['German']) else ''}">{"".join(out)}</div>
<p class="jl-meta">Text as recognised by OCR (ABBYY FineReader), without corrections. Entity mentions: TagMe (2021);
their positions were matched to this text again.</p></section>
{nav}"""
    return 200, page(f"{journal_title(D, jid)}, {date_of(doc)}", body, q=q, wide=True)


# ---------------------------------------------------------------------------------------------------- journals

def journals_view(D):
    counts = dict(S.pairs(solr.select(config.CORE, {"q": "*:*", "rows": 0, "facet": "true", "facet.field": "journal",
                                                    "facet.limit": -1})["facet_counts"]["facet_fields"]["journal"]))
    rows = []
    for jid, j in sorted(D.journals.items(), key=lambda kv: kv[1].get("title", "").lower()):
        n = counts.get(jid, 0)
        rows.append(f"""<tr data-s="{esc((j.get('title', '') + ' ' + ' '.join(j.get('place', []))).lower())}"{' class="cm-empty"' if not n else ''}>
<td><a href="{u(f"/journal/{jid}")}">{esc(j.get("title"))}</a>{f'<div class="jl-meta">{esc(j["subtitle"])}</div>' if j.get("subtitle") else ''}</td>
<td>{esc(", ".join(j.get("place", [])))}</td><td>{esc(period(j))}</td><td>{esc(", ".join(j.get("langNames", [])))}</td>
<td class="num">{fmt(n)}</td><td class="num">{pct(j["meanOcr"]) if j.get("meanOcr") else "–"}</td></tr>""")
    with_pages = sum(1 for v in counts.values() if v)
    q = (JLP + "PREFIX schema: <http://schema.org/>\nSELECT (COUNT(?j) AS ?journals) (SUM(?n) AS ?pages) WHERE {\n"
         "  ?j a schema:Periodical ; jl:indexedPages ?n .\n}")
    body = f"""<h1>Journals</h1>
<p class="jl-lead">{fmt(len(D.journals))} periodicals in the catalogue of Compact Memory {sparql_link(q)};
{fmt(with_pages)} of them have pages with full text here. Click a column title to sort.</p>
<input class="cm-filterbox" type="search" placeholder="Filter by title or place" aria-label="Filter journals" data-filter="#jt">
<div class="jl-scroll"><table class="jl-table cm-sortable" id="jt">
<thead><tr><th>Title</th><th>Place</th><th>Period</th><th>Language</th><th class="num">Pages</th><th class="num">OCR</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p class="jl-meta">OCR = mean share of known words on the journal's pages (dataset cm-ocr-quality); scripts other than
Latin score lower, as the word list is mostly German.</p>"""
    return 200, page("Journals", body, active="/journals", wide=True)


def period(j):
    ps = j.get("period", [])
    plain = [p for p in ps if re.fullmatch(r"\d{4}(-\d{4})?", p)]
    return (plain or ps or [""])[0]


def journal_view(D, jid):
    j = D.journals.get(jid)
    if not j:
        raise NotFound
    res = solr.select(config.CORE, {"q": "*:*", "fq": f"journal:{solr.quote(jid)}", "rows": 0, "facet": "true",
                                    "facet.mincount": 1, "facet.field": ["year", "ep", "lang"],
                                    "f.year.facet.limit": -1, "f.year.facet.sort": "index", "f.ep.facet.limit": 20,
                                    "stats": "true", "stats.field": "ocr"})
    total = res["response"]["numFound"]
    years = [(int(y), c) for y, c in S.facet(res, "year")]
    ents = [(int(v), c) for v, c in S.facet(res, "ep")]
    facts = []
    if j.get("subtitle"):
        facts.append(("Subtitle", j["subtitle"]))
    if j.get("place"):
        facts.append(("Place", ", ".join(j["place"])))
    if j.get("period"):
        facts.append(("Period", " · ".join(j["period"])))
    if j.get("publisher"):
        facts.append(("Publisher", " · ".join(j["publisher"])))
    if j.get("langNames"):
        facts.append(("Language", ", ".join(j["langNames"])))
    if j.get("issued"):
        facts.append(("Digitised", j["issued"]))
    qj = (JLP + "SELECT ?pages ?ocr WHERE {\n"
          f"  <{cm_iri(jid)}> jl:indexedPages ?pages .\n  OPTIONAL {{ <{cm_iri(jid)}> jl:meanOcrKnownWordShare ?ocr }}\n}}")
    facts.append(("Pages", f'{fmt(total)} with full text here' +
                  (f' · {fmt(j["indexedPages"])} in the graph {sparql_link(qj)}' if "indexedPages" in j else ""), True))
    if j.get("meanOcr"):
        facts.append(("OCR quality", f'{pct(j["meanOcr"])} known words on average {sparql_link(qj)}', True))
    links = [f'<a href="{esc(config.UB_TITLE.format(vlid=jid))}">Visual Library</a>']
    for s in j.get("sameAs", []):
        if "zdb" in s:
            zid = s.rsplit("/", 1)[-1]
            links.append(f'<a href="https://zdb-katalog.de/title.xhtml?idn={esc(zid)}">ZDB {esc(zid)}</a>')
    for s in j.get("seeAlso", []):
        if "nbn-resolving" in s:
            links.append(f'<a href="{esc(s)}">URN</a>')
    links.append(f'<a href="{esc(platform(cm_iri(jid)))}">IRI in JudaicaLink</a>')
    facts.append(("Links", " · ".join(links), True))
    dl = "".join(f"<dt>{esc(f[0])}</dt><dd>{f[1] if len(f) > 2 else esc(f[1])}</dd>" for f in facts)
    kids = D.children.get(jid, [])
    units = units_list(D, kids)
    chips = "".join(f'<a class="cm-chip cm-{esc(D.entities[n]["cls"])}" href="{u("/search", e=n, j=jid)}">'
                    f'{esc(D.entities[n]["label"])} <span class="cm-n">{fmt(c)}</span></a>' for n, c in ents if n in D.entities)
    body = f"""<nav class="cm-crumbs"><a href="{u("/journals")}">Journals</a> › journal</nav>
<h1>{esc(j.get("title"))}</h1>
<dl class="jl-facts">{dl}</dl>
<form class="cm-form cm-inline" action="{u("/search")}"><input type="hidden" name="j" value="{esc(jid)}">
<input type="search" name="q" placeholder="Search in this journal" aria-label="Search in this journal">
<button class="jl-button" type="submit">Search</button></form>
<section><h2>Pages per year</h2>{bars(years, href=lambda y: u("/search", j=jid, from_=y, to=y))}</section>
{f'<section><h2>Most mentioned</h2><div class="cm-chips">{chips}</div></section>' if chips else ''}
<section><h2>Volumes and issues</h2>{units or '<p class="jl-meta">None in the graph.</p>'}</section>"""
    return 200, page(j.get("title"), body, active="/journals")


def units_list(D, kids, limit=600):
    if not kids:
        return ""
    lis = []
    for k in kids[:limit]:
        n = D.nodes[k]
        sub = len(D.children.get(k, []))
        lis.append(f'<li><a href="{u(f"/issue/{k}")}">{esc(node_label(n))}</a>'
                   f'<span class="jl-meta"> {esc(NODE_TYPES.get(n.get("t"), ""))}{(", " + esc(n["d"][:10])) if n.get("d") and n["d"][:4] not in node_label(n) else ""}'
                   f'{f", {sub} parts" if sub else ""}</span></li>')
    more = f'<li class="jl-meta">… and {len(kids) - limit} more</li>' if len(kids) > limit else ""
    return f'<ul class="cm-units">{"".join(lis)}{more}</ul>'


def issue_view(D, nid, params):
    n = D.nodes.get(nid)
    if not n:
        raise NotFound
    p = (params.get("p") or ["1"])[0]
    p = max(1, min(200, int(p))) if p.isdigit() else 1
    rows = 60
    res = solr.select(config.CORE, {"q": "*:*", "fq": f"units:{solr.quote(nid)}", "fl": "id,label,seq,date,parent",
                                    "sort": "date asc,parent asc,seq asc,id asc", "rows": rows,
                                    "start": (p - 1) * rows})
    total = res["response"]["numFound"]
    jid = D.journal_of(nid)
    thumbs = "".join(f'<li><a href="{u(f"/page/{d["id"]}")}"><img loading="lazy" src="{iiif(d["id"])}" alt="" width="100" '
                     f'height="140"><span>{esc(d.get("label") or d.get("seq", ""))}</span></a></li>'
                     for d in res["response"]["docs"])
    kids = D.children.get(nid, [])
    facts = [("Type", NODE_TYPES.get(n.get("t"), n.get("t")) + (f" ({n['ty']})" if n.get("ty") else ""))]
    if n.get("d"):
        facts.append(("Date", n["d"]))
    facts.append(("Pages", fmt(total)))
    facts.append(("Links", f'<a href="{esc(config.UB_TITLE.format(vlid=nid))}">Visual Library</a> · '
                           f'<a href="{esc(platform(cm_iri(nid)))}">IRI in JudaicaLink</a>', True))
    dl = "".join(f"<dt>{esc(f[0])}</dt><dd>{f[1] if len(f) > 2 else esc(f[1])}</dd>" for f in facts)
    a = {"p": p}
    last = (total + rows - 1) // rows
    pg = ""
    if last > 1:
        pg = '<nav class="cm-pager">' + (f'<a href="{u(f"/issue/{nid}", p=p - 1)}">← Previous</a>' if p > 1 else "") + \
             f"<span>Pages {(p - 1) * rows + 1}–{min(p * rows, total)} of {fmt(total)}</span>" + \
             (f'<a href="{u(f"/issue/{nid}", p=p + 1)}">Next →</a>' if p < last else "") + "</nav>"
    body = f"""{breadcrumbs(D, n.get("p") if n.get("p") not in D.journals else None, jid)}
<h1>{esc(node_label(n))}</h1>
<p class="jl-lead"><a href="{u(f"/journal/{jid}")}">{esc(journal_title(D, jid))}</a></p>
<dl class="jl-facts">{dl}</dl>
{f'<section><h2>Parts</h2>{units_list(D, kids)}</section>' if kids else ''}
<section><h2>Pages</h2>{f'<ul class="cm-thumbs">{thumbs}</ul>' if thumbs else '<p class="jl-meta">No pages with full text.</p>'}{pg}</section>"""
    return 200, page(f"{node_label(n)} · {journal_title(D, jid)}", body, active="/journals", wide=True)


def not_found(msg="This page does not exist."):
    return 404, page("Not found", f'<h1>Not found</h1><p>{esc(msg)}</p><p><a href="{u("/")}">Compact Memory</a></p>')
