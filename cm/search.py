"""The search: request parameters -> Solr query -> results and facets.

Parameters (all optional, repeatable where it makes sense):
  q      full-text query (edismax over the OCR text and the article title; all words must occur)
  e      entity-page number: pages mentioning this entity (several: all of them)
  occ    occupation label: pages mentioning a person with this occupation (several: all)
  bp     geonames id: pages mentioning a person born there (several: all)
  pl     entity-page number of a place: pages mentioning that place (several: all)
  bd     decade (1840): pages mentioning a person born in that decade (several: all)
  cls    entity class (person, place, subject): pages mentioning one of them
  j      journal VLID (several: any)
  lang   language (several: any)
  pt     page type, i.e. the unit a page belongs to (several: any)
  from, to   year range
  sort   rel (default with q), date (default without q), -date
  p      result page (1-based)
"""

import json
import re

from . import config, solr
from .solr import quote

ROWS = 20
MULTI_OR = {"j": "journal", "lang": "lang", "pt": "ptype", "cls": "eclass"}     # any of the selected values
MULTI_AND = {"e": "ep", "occ": "occ", "bp": "bplace", "pl": "ep_place", "bd": "bdecade"}          # all of the selected values
SNIPPET = 240


def clean(params):
    """The search parameters, checked and bounded."""
    g = lambda k: params.get(k, [])
    out = {"q": (g("q")[:1] or [""])[0].strip()[:500]}
    for k in ("e", "pl", "bd"):
        out[k] = [x for x in dict.fromkeys(g(k)) if x.isdigit() and len(x) < 12][:10]
    for k in ("occ", "bp", "j", "lang", "pt", "cls"):
        out[k] = [x[:200] for x in dict.fromkeys(g(k)) if x.strip()][:20]
    for k in ("from", "to"):
        v = (g(k)[:1] or [""])[0]
        out[k] = int(v) if re.fullmatch(r"\d{4}", v) else None
    s = (g("sort")[:1] or [""])[0]
    out["sort"] = s if s in ("rel", "date", "-date") else ("rel" if out["q"] else "date")
    p = (g("p")[:1] or ["1"])[0]
    out["p"] = max(1, min(500, int(p))) if p.isdigit() else 1
    out["all"] = (g("all")[:1] or [""])[0][:20]
    return out


def active(a):
    return bool(a["q"] or any(a[k] for k in (*MULTI_OR, *MULTI_AND)) or a["from"] or a["to"])


def filters(a, skip=None):
    fq = []
    for k, field in MULTI_OR.items():
        if a[k]:
            fq.append(f"{{!tag={k}}}{field}:(" + " OR ".join(quote(v) for v in a[k]) + ")")
    for k, field in MULTI_AND.items():
        for v in a[k]:
            fq.append(f"{field}:{quote(v)}")
    if a["from"] or a["to"]:
        fq.append(f"{{!tag=yr}}year:[{a['from'] or '*'} TO {a['to'] or '*'}]")
    return fq


def query(a, rows=ROWS, facets=True, facet_limit=None):
    params = {
        "fl": "id,iri,journal,parent,volume,issue,article,date,year,label,seq,pageno,ptype,lang,ocr,n_ent,mentions"
              + ("" if a["q"] else ",text"),
        "rows": rows, "start": (a["p"] - 1) * rows, "fq": filters(a),
    }
    if a["q"]:
        params.update({"defType": "edismax", "q": a["q"], "qf": "text article^2", "pf": "text^3",
                       "q.op": "AND", "hl": "true", "hl.method": "unified", "hl.fl": "text", "hl.snippets": 2,
                       "hl.fragsize": 180, "hl.tag.pre": "<mark>", "hl.tag.post": "</mark>",
                       "hl.encoder": "html", "hl.maxAnalyzedChars": 100000})
    else:
        params["q"] = "*:*"
    params["sort"] = {"rel": "score desc,date asc", "date": "date asc,id asc", "-date": "date desc,id asc"}[a["sort"]]
    if facets:
        lim = facet_limit or {}
        params.update({
            "facet": "true", "facet.mincount": 1,
            "facet.field": ["{!ex=j}journal", "{!ex=lang}lang", "{!ex=pt}ptype", "{!ex=cls}eclass", "occ", "bplace",
                            "ep_place", "ep", "{!ex=yr}year", "bdecade"],
            "f.journal.facet.limit": lim.get("j", 12), "f.occ.facet.limit": lim.get("occ", 12),
            "f.bplace.facet.limit": lim.get("bp", 12), "f.ep_place.facet.limit": lim.get("pl", 12),
            "f.ep.facet.limit": 16, "f.year.facet.limit": -1, "f.year.facet.sort": "index",
            "f.ptype.facet.limit": 12, "f.bdecade.facet.limit": -1, "f.bdecade.facet.sort": "index",
        })
    return solr.select(config.CORE, params)


def pairs(flat):
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]


def facet(res, name):
    return pairs(res.get("facet_counts", {}).get("facet_fields", {}).get(name, []))


def mention_snippet(text, mentions, eps, width=SNIPPET):
    """An escaped excerpt of text around the first mention of one of eps (or of any entity), mention marked."""
    from .html import esc
    ms = [m for m in mentions if m[1] >= 0]
    pick = next((m for m in ms if str(m[0]) in eps), None) or (ms[0] if ms else None)
    if not pick:
        return esc(text[:width]) + ("…" if len(text) > width else "")
    s, e = pick[1], pick[2]
    a = max(0, s - width // 2)
    b = min(len(text), e + width // 2)
    return (("…" if a else "") + esc(text[a:s]) + "<mark class=\"cm-ent\">" + esc(text[s:e]) + "</mark>"
            + esc(text[e:b]) + ("…" if b < len(text) else ""))


def mentions_of(doc):
    try:
        return json.loads(doc.get("mentions") or "[]")
    except ValueError:
        return []
