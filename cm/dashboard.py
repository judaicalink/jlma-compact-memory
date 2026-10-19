"""Job `dashboard`: the Compact Memory dashboard, a static page in DATA/dashboard/index.html.

Ported from the CM view of the workspace's data-profile dashboard (dashboard/aggregate.py, template.html), with
three changes: the OCR quality comes from the graph (cm-ocr-quality, the same measure as the earlier word-list
estimate, now published), the journals' facts from compact-memory-journals, and a new section "Compact Memory in
the graph" whose figures are SPARQL queries on the platform's endpoint, each linked to the query editor.

What only the full text can tell (words, pages per year and language, metadata coverage, excerpts, dropped pages)
comes from a light pass over the bundle (about a minute on 4 cores).
"""

import collections
import csv
import gzip

import json
import multiprocessing
import sys
import time
import urllib.parse
from pathlib import Path

from . import config, sparql
from .html import page

P = """PREFIX jl: <http://data.judaicalink.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""
G = "http://data.judaicalink.org/datasets/"

QUERIES = {
    "pages": ("Pages in the graph", P + """SELECT (COUNT(?page) AS ?pages) WHERE {
  GRAPH <%scompact-memory> { ?page a jl:Page }
}""" % G),
    "journals": ("Journals in the catalogue, and those with pages", P + """SELECT (COUNT(?j) AS ?journals) (SUM(IF(?n > 0, 1, 0)) AS ?withPages) WHERE {
  ?j a schema:Periodical ; jl:indexedPages ?n .
}"""),
    "mentions": ("Entity mentions found by TagMe, and the entities", P + """SELECT (COUNT(?ref) AS ?mentions) (COUNT(DISTINCT ?entity) AS ?entities) WHERE {
  ?entity jl:hasReference ?ref .
}"""),
    "linked_pages": ("Pages with at least one mention", P + """SELECT (COUNT(DISTINCT ?page) AS ?pages) WHERE {
  ?ref jl:isOnPage ?p .
  OPTIONAL { ?cur owl:sameAs ?p }          # mentions on pages of the 2021 IRIs
  BIND(COALESCE(?cur, ?p) AS ?page)
}"""),
    "classes": ("The mentioned entities by the class of their entity page", P + """SELECT ?class (COUNT(DISTINCT ?entity) AS ?entities) WHERE {
  ?entity jl:hasReference [] .
  OPTIONAL { ?entity dcterms:isReplacedBy ?cur }   # the TagMe entities replaced by the dbpedia records per language
  BIND(COALESCE(?cur, ?entity) AS ?r)
  ?ep jl:sameAs|jl:represents ?r ; a ?class .
  FILTER(?class != jl:EntityPage)
} GROUP BY ?class ORDER BY DESC(?entities)"""),
    "pages_year": ("Pages per year (date of the issue)", P + """SELECT ?year (COUNT(?page) AS ?pages) WHERE {
  ?page a jl:Page ; jl:belongsToIssue ?u .
  ?u dcterms:date ?d .
  BIND(SUBSTR(STR(?d), 1, 4) AS ?year)
} GROUP BY ?year ORDER BY ?year"""),
    "linked_year": ("Pages with a mention, per year", P + """SELECT ?year (COUNT(DISTINCT ?page) AS ?linked) WHERE {
  ?ref jl:isOnPage ?p .
  OPTIONAL { ?cur owl:sameAs ?p }
  BIND(COALESCE(?cur, ?p) AS ?page)
  ?page jl:belongsToIssue ?u .
  ?u dcterms:date ?d .
  BIND(SUBSTR(STR(?d), 1, 4) AS ?year)
} GROUP BY ?year ORDER BY ?year"""),
    "linked_journal": ("Pages with a mention, per journal", P + """SELECT ?journal ?title ?pages (COUNT(DISTINCT ?page) AS ?linked) WHERE {
  ?ref jl:isOnPage ?p .
  OPTIONAL { ?cur owl:sameAs ?p }
  BIND(COALESCE(?cur, ?p) AS ?page)
  ?page jl:belongsToIssue ?u .
  ?u jl:belongsToJournal ?journal .
  ?journal jl:indexedPages ?pages .
  OPTIONAL { ?journal dcterms:title ?title }
} GROUP BY ?journal ?title ?pages ORDER BY DESC(?linked)"""),
    "top_entities": ("The entities on most pages", P + """SELECT ?entity ?label ?pages ?mentions ?journals ?first ?last WHERE {
  ?presence jl:entity ?entity ; jl:pageCount ?pages ; jl:mentionCount ?mentions ;
            jl:journalCount ?journals ; jl:firstMentionYear ?first ; jl:lastMentionYear ?last .
  OPTIONAL { ?entity skos:prefLabel ?label FILTER(LANG(?label) = "en") }
} ORDER BY DESC(?pages) LIMIT 40"""),
    "ocr_journal": ("Mean OCR quality per journal", P + """SELECT ?journal ?title ?share WHERE {
  ?journal jl:meanOcrKnownWordShare ?share .
  OPTIONAL { ?journal dcterms:title ?title }
} ORDER BY ?share"""),
    "ocr_hist": ("Pages by OCR quality (5% bins)", P + """SELECT ?bin (COUNT(?page) AS ?pages) WHERE {
  ?page jl:ocrKnownWordShare ?share .
  BIND(FLOOR(?share * 20) AS ?b)
  BIND(IF(?b > 19, 19, ?b) AS ?bin)
} GROUP BY ?bin ORDER BY ?bin"""),
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------------------------ the bundle

def profile_part(path):
    years = collections.defaultdict(lambda: {"pages": 0, "words": 0, "lang": collections.Counter()})
    journals = {}
    units = collections.Counter()
    for line in gzip.open(path, "rt", encoding="utf-8"):
        d = json.loads(line)
        text = d.get("text", "")
        words = len(text.split())
        year = int(d["dateIssued"][:4]) if d.get("dateIssued") else None
        lang = d.get("lang") or "not recorded"
        units[d.get("parent_type", "")] += 1
        if year:
            y = years[year]
            y["pages"] += 1
            y["words"] += words
            y["lang"][lang] += 1
        j = journals.setdefault(d["vlid_journal"], {"title": d.get("j_title", ""), "lang": collections.Counter(),
                                                   "pages": 0, "words": 0, "years": collections.Counter(),
                                                   "heft": 0, "aufsatz": 0, "volume": 0, "page_label": 0,
                                                   "samples": []})
        j["pages"] += 1
        j["words"] += words
        j["lang"][lang] += 1
        if year:
            j["years"][year] += 1
        for f in ("heft", "aufsatz", "volume", "page_label"):
            if d.get(f):
                j[f] += 1
        if j["pages"] % 97 == 1 and len(j["samples"]) < 40 and len(text) > 400:
            j["samples"].append({"id": d["id"], "date": (d.get("dateIssued") or "")[:10], "heft": d.get("heft", ""),
                                 "text": text[:420]})
    return dict(years), journals, units


def bundle_profile(bundle, workers):
    manifest = json.loads((bundle / "manifest.json").read_text("utf-8"))
    parts = [bundle / p["file"] for p in manifest["parts"]]
    years = collections.defaultdict(lambda: {"pages": 0, "words": 0, "lang": collections.Counter()})
    J, units = {}, collections.Counter()
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for y_, j_, u_ in pool.imap_unordered(profile_part, parts):
            for y, v in y_.items():
                t = years[y]
                t["pages"] += v["pages"]
                t["words"] += v["words"]
                t["lang"].update(v["lang"])
            units.update(u_)
            for jid, v in j_.items():
                if jid not in J:
                    J[jid] = v
                    continue
                r = J[jid]
                for k in ("pages", "words", "heft", "aufsatz", "volume", "page_label"):
                    r[k] += v[k]
                r["lang"].update(v["lang"])
                r["years"].update(v["years"])
                r["samples"] += v["samples"]
    return manifest, years, J, units


def dropped_per_journal(bundle, store_csv):
    """Pages left out of the bundle, per journal (through the page table of compact-memory-supp)."""
    meta = {}
    if store_csv and store_csv.exists():
        with gzip.open(store_csv, "rt", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                meta[r["VLID_Seite"]] = (r["VLID_Zs"], (r.get("Zs_Caption") or "").strip())
    dropped = collections.defaultdict(collections.Counter)
    titles = {}
    p = bundle / "dropped.tsv.gz"
    if p.exists():
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row["VLID_Seite"] in meta:
                    jid, title = meta[row["VLID_Seite"]]
                    dropped[jid][row["reason"]] += 1
                    titles.setdefault(jid, title)
    return dropped, titles


# ------------------------------------------------------------------------------------------------ the graph

def graph_figures():
    out = {}
    for key, (title, q) in QUERIES.items():
        t = time.time()
        rows = sparql.select(q)
        out[key] = {"title": title, "query": q, "seconds": round(time.time() - t, 1), "rows": rows}
        log(f"SPARQL {key}: {len(rows)} rows, {out[key]['seconds']} s")
    return out


# ------------------------------------------------------------------------------------------------ run

def run(use_sparql=True, workers=4):
    t0 = time.time()
    bundle = config.DATA / "inputs" / config.BUNDLE
    out = config.DASHBOARD
    out.mkdir(parents=True, exist_ok=True)
    gpath = out / "graph.json"
    if use_sparql:
        graph = graph_figures()
        gpath.write_text(json.dumps(graph, ensure_ascii=False), "utf-8")
    else:
        graph = json.loads(gpath.read_text("utf-8"))
    manifest, years, J, units = bundle_profile(bundle, workers)
    log("bundle profiled", len(J), "journals")
    structure = json.loads((config.PREPARED / "structure.json").read_text("utf-8"))
    rdfj = structure["journals"]
    vers = json.loads((config.PREPARED / "versions.json").read_text("utf-8"))["datasets"]
    # the page table of the 2020 export (dataset compact-memory-supp): in the store, or copied into inputs/
    supp = config.STORE / "compact-memory-supp" / vers.get("compact-memory-supp", "") / "CM_Seiten_Metadaten.csv.gz"
    if not supp.exists():
        supp = config.DATA / "inputs" / "compact-memory-supp" / "CM_Seiten_Metadaten.csv.gz"
    dropped, dtitles = dropped_per_journal(bundle, supp)
    log("dropped pages attributed:", sum(sum(c.values()) for c in dropped.values()))
    # OCR quality per page from the graph (prepared from cm-ocr-quality), joined with the bundle's years
    ocr = {}
    with gzip.open(config.PREPARED / "pages.tsv.gz", "rt", encoding="utf-8") as f:
        for line in f:
            v, iri, parent, seq, q, m = line.split("\t", 5)
            if q:
                ocr[v] = float(q)
    jhist = collections.defaultdict(lambda: [0] * 10)
    yq = collections.defaultdict(lambda: [0.0, 0])
    for part in manifest["parts"]:
        for line in gzip.open(bundle / part["file"], "rt", encoding="utf-8"):
            # only the few fields needed: id, journal, year
            i = line.find('"id": "')
            vid = line[i + 7:line.index('"', i + 7)]
            q = ocr.get(vid)
            if q is None:
                continue
            j = line.find('"vlid_journal": "')
            jid = line[j + 17:line.index('"', j + 17)]
            jhist[jid][min(9, int(q * 10))] += 1
            k = line.find('"dateIssued": "')
            if k >= 0:
                y = int(line[k + 15:k + 19])
                yq[y][0] += q
                yq[y][1] += 1
    log("ocr joined")
    journals = []
    for jid in set(J) | set(dropped) | set(rdfj):
        r = J.get(jid, {"title": "", "lang": collections.Counter(), "pages": 0, "words": 0,
                        "years": collections.Counter(), "heft": 0, "aufsatz": 0, "volume": 0, "page_label": 0,
                        "samples": []})
        rj = rdfj.get(jid, {})
        title = rj.get("title") or r["title"] or dtitles.get(jid) or jid
        mq = rj.get("meanOcr")
        sample = None
        if r["samples"]:
            sample = dict(r["samples"][len(r["samples"]) // 2])
            sample["q"] = ocr.get(sample["id"])
        journals.append({
            "id": jid, "title": title, "lang": r["lang"].most_common(1)[0][0] if r["lang"] else "",
            "place": ", ".join(rj.get("place", [])), "pages": r["pages"], "words": r["words"], "q": mq,
            "qhist": jhist.get(jid, [0] * 10), "years": {str(y): n for y, n in sorted(r["years"].items())},
            "cov": {f: round(r[f] / r["pages"], 4) if r["pages"] else 0 for f in ("heft", "aufsatz", "volume",
                                                                                 "page_label")},
            "dropped": dict(dropped.get(jid, {})), "sample": sample, "inGraph": jid in rdfj,
        })
    journals.sort(key=lambda j: -j["pages"])
    qhist = [0] * 20
    for q in ocr.values():
        qhist[min(19, int(q * 20))] += 1
    data = {
        "manifest": {k: manifest.get(k) for k in ("created", "docs", "dropped", "notes", "changes", "date_review")},
        "bundle": config.BUNDLE, "versions": vers, "built": time.strftime("%Y-%m-%d"),
        "years": {str(y): {"pages": v["pages"], "words": v["words"],
                           "q": round(yq[y][0] / yq[y][1], 4) if yq[y][1] else None, "lang": dict(v["lang"])}
                  for y, v in sorted(years.items())},
        "qhist": qhist, "parent_types": dict(units.most_common()), "journals": journals,
        "graph": {k: {"title": v["title"], "seconds": v["seconds"], "rows": v["rows"],
                      "href": editor(v["query"])} for k, v in graph.items()},
        "queries": [{"key": k, "title": v["title"], "query": v["query"], "seconds": v["seconds"],
                     "rows": len(v["rows"]), "href": editor(v["query"])} for k, v in graph.items()],
        "base": config.BASE,
    }
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    tpl = (Path(__file__).parent / "dashboard.html").read_text("utf-8")
    body = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    (out / "index.html").write_text(page("Dashboard", body, active="/dashboard/", wide=True,
                                         head=f'<link rel="stylesheet" href="{config.BASE}/static/dashboard.css">',
                                         description="Compact Memory in figures: pages over time, journals, "
                                                     "OCR quality, data issues, and the links into the knowledge graph."),
                                    "utf-8")
    log(f"written {out / 'index.html'} in {time.time() - t0:.0f} s")


def editor(query):
    return config.SPARQL_EDITOR + "#" + urllib.parse.urlencode({"query": query, "endpoint": "/sparql"},
                                                              quote_via=urllib.parse.quote)
