"""Job `prepare`: read the RDF of the loaded versions (the store) and write what the indexer and the app need.

Inputs (newest version of each, under STORE/<slug>/<version>/): compact-memory (journals, pages, volumes, issues,
articles), cm-ocr-quality, cm-tagme (references and the 5,445 TagMe entities), cm-entities (presence, Wikidata
facts) and ep (the entity page that represents each TagMe entity, and place pages for birth places).

Outputs in DATA/prepared/:
  versions.json      the dataset versions used
  structure.json     journals and the nodes of the Visual Library tree (volumes, issues, articles)
  entities.json      the 5,445 entities, keyed by entity-page number, with the facts the search facets use
  pages.tsv.gz       one row per page: VLID, IRI (local part), parent node, sequence, OCR share, mentions (JSON)
"""

import collections
import gzip
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

from . import config
from .ttl import RDF_TYPE, Lit, triples

JL = "http://data.judaicalink.org/ontology/"
CM = "http://data.judaicalink.org/data/compact-memory/"
EP = "http://data.judaicalink.org/data/ep/"
DBP = "http://data.judaicalink.org/data/dbpedia/"
GEO = "http://data.judaicalink.org/data/geonames/"
OCC = "http://data.judaicalink.org/data/occupation/"
TAGME = "http://data.judaicalink.org/data/cm-tagme/"
DCT = "http://purl.org/dc/terms/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
OWL_SAME = "http://www.w3.org/2002/07/owl#sameAs"
FOAF = "http://xmlns.com/foaf/0.1/"
SCHEMA = "http://schema.org/"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
GEOSPARQL = "http://www.opengis.net/ont/geosparql#asWKT"
GEONAMES_RE = re.compile(r"^https?://sws\.geonames\.org/(\d+)/?$")
ISO639 = "http://id.loc.gov/vocabulary/iso639-2/"

CLASSES = {FOAF + "Person": "person", JL + "Place": "place", JL + "Subject": "subject", JL + "Work": "work",
           FOAF + "Organization": "organization"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def versions(store=None):
    """slug -> newest version directory name (the store holds the loaded versions)."""
    store = Path(store or config.STORE)
    out = {}
    for slug in config.DATASETS:
        d = store / slug
        vs = sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []
        if vs:
            out[slug] = vs[-1]
    return out


def path(store, vers, slug, name):
    return Path(store) / slug / vers[slug] / name


def lit(o):
    return o.value if isinstance(o, Lit) else o


def year_of(v):
    m = re.match(r"^(-?\d{3,4})", v or "")
    return int(m.group(1)) if m else None


def occ_label(iri):
    s = urllib.parse.unquote(iri[len(OCC):]).replace("_", " ").strip()
    return s[:1].upper() + s[1:]


# ---------------------------------------------------------------------------------------------------------------

def read_journals(store, vers):
    J = {}
    for s, p, o in triples(path(store, vers, "compact-memory", "compact-memory-journals.ttl.gz")):
        if not s.startswith(CM):
            continue
        jid = s[len(CM):]
        j = J.setdefault(jid, {})
        k = p.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        if p == RDF_TYPE:
            j["type"] = o
        elif p == DCT + "language":
            j.setdefault("lang", []).append(o[len(ISO639):] if o.startswith(ISO639) else o)
        elif p in (JL + "publicationPeriod", JL + "placeOfPublication", DCT + "publisher", RDFS + "seeAlso",
                   OWL_SAME):
            j.setdefault({"publicationPeriod": "period", "placeOfPublication": "place", "publisher": "publisher",
                          "seeAlso": "seeAlso", "sameAs": "sameAs"}[k], []).append(lit(o))
        elif p == DCT + "title":
            j["title"] = lit(o)
        elif p == JL + "subtitle":
            j["subtitle"] = lit(o)
        elif p == DCT + "identifier":
            j["urn"] = lit(o)
        elif p == DCT + "issued":
            j["issued"] = lit(o)
        elif p == JL + "indexedPages":
            j["indexedPages"] = int(lit(o))
        elif p == DCT + "description":
            j["description"] = lit(o)
    corpus = J.pop("corpus", {})
    for j in J.values():
        for k in ("period", "place", "publisher", "seeAlso", "sameAs", "lang"):
            if k in j:
                j[k] = sorted(set(j[k]))
    return J, corpus


def read_pages(store, vers):
    """Nodes (volumes, issues, articles) and pages of the compact-memory dataset."""
    nodes, pages = {}, {}
    types = {SCHEMA + "PublicationVolume": "volume", SCHEMA + "PublicationIssue": "issue", SCHEMA + "Article": "article"}
    for s, p, o in triples(path(store, vers, "compact-memory", "compact-memory-pages.ttl.gz")):
        loc = s[len(CM):]
        if "--" in loc:                                         # a page: <j>-<v>-<i>--<prefix>-<VLID>
            vlid = loc.rsplit("-", 1)[1]
            pg = pages.get(vlid)
            if pg is None:
                pg = pages[vlid] = {"iri": loc}
            if p == JL + "belongsToIssue":
                pg["parent"] = o[len(CM):]
            elif p == JL + "pageSequence":
                pg["seq"] = int(lit(o))
            elif p == OWL_SAME:
                pg.setdefault("old", []).append(o[len(CM):])
            continue
        n = nodes.setdefault(loc, {})
        if p == RDF_TYPE:
            n["t"] = types.get(o, o)
        elif p == RDFS + "label":
            n["l"] = lit(o)
        elif p == DCT + "date":
            n["d"] = lit(o)
        elif p == DCT + "isPartOf":
            n["p"] = o[len(CM):]
        elif p == JL + "belongsToJournal":
            n["j"] = o[len(CM):]
        elif p == DCT + "type":
            n["ty"] = lit(o)
    return nodes, pages


def read_ocr(store, vers):
    page_q, journal_q = {}, {}
    for s, p, o in triples(path(store, vers, "cm-ocr-quality", "cm-ocr-quality.ttl.gz")):
        loc = s[len(CM):]
        if p == JL + "ocrKnownWordShare":
            page_q[loc.rsplit("-", 1)[1]] = float(lit(o))
        elif p == JL + "meanOcrKnownWordShare":
            journal_q[loc] = float(lit(o))
    return page_q, journal_q


def read_tagme(store, vers):
    refs = {}
    keep = {JL + "hasSpot": "spot", JL + "hasStart": "start", JL + "hasEnd": "end", JL + "hasRho": "rho",
            JL + "hasLinkProb": "lp"}
    for s, p, o in triples(path(store, vers, "cm-tagme", "cm_tagme_references.ttl.gz")):
        r = refs.setdefault(s[len(TAGME):], {})
        if p == JL + "isOnPage":
            r["vlid"] = o.rsplit("-", 1)[1]
        elif p in keep:
            r[keep[p]] = lit(o)
    entity_refs = collections.defaultdict(list)
    for s, p, o in triples(path(store, vers, "cm-tagme", "cm_tagme_resources.ttl.gz")):
        if p == JL + "hasReference":
            entity_refs[s].append(o[len(TAGME):])
    return refs, entity_refs


def read_cm_entities(store, vers):
    presence, wikidata = {}, collections.defaultdict(dict)
    for s, p, o in triples(path(store, vers, "cm-entities", "cm-entities-presence.ttl.gz")):
        if p == RDF_TYPE:
            continue
        pr = presence.setdefault(s, {})
        k = p.rsplit("/", 1)[-1]
        pr[k] = lit(o)
    by_entity = {pr["entity"]: pr for pr in presence.values() if "entity" in pr}
    for s, p, o in triples(path(store, vers, "cm-entities", "cm-entities-wikidata.ttl.gz")):
        w = wikidata[s]
        if p == SKOS + "prefLabel" and isinstance(o, Lit):
            w.setdefault("labels", {})[o.lang or ""] = o.value
        elif p == OWL_SAME:
            w.setdefault("sameAs", []).append(o)
        elif p == GEOSPARQL:
            w["wkt"] = lit(o)
        elif p == FOAF + "isPrimaryTopicOf":
            w["wikipedia"] = o
        elif p == RDF_TYPE:
            w["type"] = o
    return by_entity, wikidata


def read_ep(store, vers, tagme_entities):
    """Two passes over ep.ttl.gz: first which page represents which TagMe entity and the geonames ids of place
    pages (for birth places), then every fact of the pages that represent TagMe entities."""
    f = path(store, vers, "ep", "ep.ttl.gz")
    rep, geo_ep, labels, place_ep = {}, {}, {}, set()
    for s, p, o in triples(f):
        if p == JL + "represents" and o in tagme_entities:
            rep.setdefault(o, set()).add(s)
        elif p == OWL_SAME and isinstance(o, str):
            m = GEONAMES_RE.match(o)
            if m:
                geo_ep.setdefault(m.group(1), set()).add(s)
        elif p == RDF_TYPE and o == JL + "Place":
            place_ep.add(s)
        elif p == SKOS + "prefLabel" and isinstance(o, Lit):
            labels.setdefault(s, o.value)
    geo_ep = {g: sorted(e for e in eps if e in place_ep) for g, eps in geo_ep.items()}
    geo_ep = {g: eps for g, eps in geo_ep.items() if eps}
    wanted = {e for eps in rep.values() for e in eps}
    facts = collections.defaultdict(lambda: collections.defaultdict(list))
    for s, p, o in triples(f):
        if s in wanted:
            facts[s][p].append(o)
    return rep, facts, geo_ep, labels


# ---------------------------------------------------------------------------------------------------------------

def ep_num(iri):
    return int(iri[len(EP):])


def first(vals):
    return lit(vals[0]) if vals else None


def build_entities(tagme_entities, rep, facts, geo_ep, ep_labels, presence, wikidata, journals):
    E = {}
    multi = 0
    for ent in sorted(tagme_entities):
        eps = sorted(rep.get(ent, ()), key=ep_num)
        if not eps:
            continue
        if len(eps) > 1:
            multi += 1
        e = eps[0]
        if ep_num(e) in E:                                  # one entity page for several TagMe entities
            E[ep_num(e)]["tagme"].append(ent[len(DBP):])
            continue
        F = facts[e]
        cls = [CLASSES[t] for t in F.get(RDF_TYPE, []) if t in CLASSES]
        w = wikidata.get(ent, {})
        wl = w.get("labels", {})
        pref = first(F.get(SKOS + "prefLabel"))
        alts = sorted({lit(x) for x in F.get(SKOS + "altLabel", [])} | {v for v in wl.values()}
                      | {ent[len(DBP):].replace("_", " ")} | ({pref} if pref else set()))
        label = wl.get("en") or wl.get("de") or ent[len(DBP):].replace("_", " ")
        same = [x for x in F.get(OWL_SAME, []) if isinstance(x, str)] + w.get("sameAs", [])
        ids = {}
        for x in same:
            if m := re.match(r"^https?://d-nb\.info/gnd/([^/]+)$", x):
                ids.setdefault("gnd", m.group(1))
            elif m := re.match(r"^https?://viaf\.org/viaf/(\d+)/?$", x):
                ids.setdefault("viaf", m.group(1))
            elif m := re.match(r"^https?://www\.wikidata\.org/entity/(Q\d+)$", x):
                ids.setdefault("wikidata", m.group(1))
            elif m := GEONAMES_RE.match(x):
                ids.setdefault("geonames", m.group(1))
        born = first(F.get(JL + "birthDateNormalized")) or first(F.get(JL + "birthDate"))
        died = first(F.get(JL + "deathDateNormalized")) or first(F.get(JL + "deathDate"))
        rec = {"ep": ep_num(e), "tagme": [ent[len(DBP):]], "cls": cls[0] if cls else "other", "label": label,
               "pref": pref or label, "alt": [a for a in alts if a != label]}
        if born:
            rec["born"] = born
        if died:
            rec["died"] = died
        by = year_of(born)
        if by is not None:
            rec["by"] = by
        for key, prop in (("bplace", "birthLocation"), ("dplace", "deathLocation")):
            uris = [x for x in F.get(JL + prop + "URI", []) if isinstance(x, str) and x.startswith(GEO)]
            name = first(F.get(JL + prop))
            if uris or name:
                rec[key] = {"gid": uris[0][len(GEO):] if uris else None, "name": name}
        occ = sorted({occ_label(x) for x in F.get(JL + "occupationURI", []) if isinstance(x, str) and x.startswith(OCC)})
        if occ:
            rec["occ"] = occ
        ab = first(F.get(JL + "hasAbstract"))
        if ab:
            rec["abstract"] = re.sub(r"\s+", " ", ab).strip()[:600]
        if ids:
            rec["ids"] = ids
        if "wikipedia" in w:
            rec["wikipedia"] = w["wikipedia"]
        if "wkt" in w and (m := re.match(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)", w["wkt"])):
            rec["point"] = [round(float(m.group(1)), 5), round(float(m.group(2)), 5)]
        pr = presence.get(ent)
        if pr:
            rec["presence"] = {k: (int(v) if str(v).lstrip("-").isdigit() else v) for k, v in pr.items()
                               if k in ("mentionCount", "pageCount", "journalCount", "firstMentionYear",
                                        "lastMentionYear")}
            mfj = pr.get("mostFrequentJournal", "")
            if mfj.startswith(CM):
                rec["presence"]["topJournal"] = mfj[len(CM):]
        E[rec["ep"]] = rec
    # birth places: the place page with that geonames id, else the most frequent literal
    names = collections.defaultdict(collections.Counter)
    for rec in E.values():
        bp = rec.get("bplace")
        if bp and bp["gid"] and bp["name"]:
            names[bp["gid"]][bp["name"]] += 1
    places = {}
    for rec in E.values():
        bp = rec.get("bplace")
        if not bp or not bp["gid"]:
            continue
        g = bp["gid"]
        if g in places:
            continue
        eps = geo_ep.get(g, [])
        place_rec = next((E[ep_num(x)] for x in eps if ep_num(x) in E), None)
        if place_rec:
            places[g] = {"name": place_rec["label"], "ep": place_rec["ep"]}
        elif eps:
            places[g] = {"name": ep_labels.get(eps[0]) or names[g].most_common(1)[0][0], "ep": ep_num(eps[0])}
        else:
            places[g] = {"name": names[g].most_common(1)[0][0] if names[g] else g}
    return E, places, multi


def run(store=None, out=None):
    store = Path(store or config.STORE)
    out = Path(out or config.PREPARED)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    vers = versions(store)
    missing = [s for s in config.DATASETS if s not in vers]
    if missing:
        sys.exit(f"missing in the store {store}: {missing}")
    log("versions", vers)

    journals, corpus = read_journals(store, vers)
    log("journals", len(journals))
    nodes, pages = read_pages(store, vers)
    log("nodes", len(nodes), collections.Counter(n.get("t") for n in nodes.values()), "pages", len(pages))
    page_q, journal_q = read_ocr(store, vers)
    for jid, q in journal_q.items():
        journals.setdefault(jid, {})["meanOcr"] = q
    log("ocr pages", len(page_q), "journals", len(journal_q))
    refs, entity_refs = read_tagme(store, vers)
    log("references", len(refs), "entities", len(entity_refs))
    presence, wikidata = read_cm_entities(store, vers)
    log("presence", len(presence), "wikidata", len(wikidata))
    rep, facts, geo_ep, ep_labels = read_ep(store, vers, set(entity_refs))
    log("represented", len(rep), "geonames ids with a place page", len(geo_ep))
    entities, places, multi = build_entities(set(entity_refs), rep, facts, geo_ep, ep_labels, presence, wikidata,
                                             journals)
    log("entities", len(entities), collections.Counter(e["cls"] for e in entities.values()),
        "with several pages", multi, "birth places", len(places))

    # mentions per page (VLID), only of entities with an entity page
    ent_ep = {DBP + t: n for n, e in entities.items() for t in e["tagme"]}
    mentions = collections.defaultdict(list)
    no_page = 0
    for ent, rs in entity_refs.items():
        n = ent_ep.get(ent)
        if n is None:
            continue
        for r in rs:
            x = refs.get(r)
            if not x or "vlid" not in x:
                no_page += 1
                continue
            mentions[x["vlid"]].append([n, int(x.get("start", -1)), int(x.get("end", -1)), x.get("spot", ""),
                                        int(r), round(float(x.get("rho", 0)), 3)])
    unknown = sum(1 for v in mentions if v not in pages)
    log("pages with mentions", len(mentions), "not in compact-memory", unknown, "references without page", no_page)

    # nodes: the chain of each node up to its journal
    for n in nodes.values():                 # dcterms:type is kept only where it says more than the class
        if n.get("ty") in ("journal issue", "journal volume", "article"):
            del n["ty"]
        n.setdefault("t", "unit")
    with gzip.open(out / "pages.tsv.gz", "wt", encoding="utf-8") as f:
        for vlid in sorted(pages, key=int):
            pg = pages[vlid]
            ms = sorted(mentions.get(vlid, []), key=lambda m: m[1])
            q = page_q.get(vlid)
            f.write("\t".join([vlid, pg["iri"], pg.get("parent", ""), str(pg.get("seq", "")),
                               "" if q is None else f"{q:.4f}", json.dumps(ms, ensure_ascii=False) if ms else ""]) + "\n")
    # pages that only TagMe knows (2021 IRIs whose VLID is no longer a page) are kept out
    structure = {"journals": journals, "corpus": corpus, "nodes": nodes}
    (out / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, separators=(",", ":")), "utf-8")
    (out / "entities.json").write_text(json.dumps({"entities": entities, "birthplaces": places},
                                                  ensure_ascii=False, separators=(",", ":")), "utf-8")
    (out / "versions.json").write_text(json.dumps({"datasets": vers, "prepared": time.strftime("%Y-%m-%d")},
                                                  indent=1), "utf-8")
    log(f"written to {out} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    run(*sys.argv[1:3])
