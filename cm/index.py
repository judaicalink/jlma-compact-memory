"""Job `index`: the full-text bundle plus the prepared graph data -> the Solr core of the pages.

The core is built under a new name (<core>_b<timestamp>), which must exist and be empty (bin/index.sh creates it
with `solr create`, which gives the core its own copy of the _default configset, see decision 0004), filled,
committed, checked against the bundle's manifest, and then swapped in for <core>; the old core is dropped. A new
name per build, because a core keeps its instance directory when it is swapped or renamed. Searches never see a half-built index.

Per page the index holds the bundle's fields (journal, volume, issue, article, date, page, language, text) and
what the graph says: the page IRI, its place in the tree of the Visual Library, its OCR share (cm-ocr-quality),
and the entities it mentions (cm-tagme -> ep) with derived facets: class, occupations and birth places of the
persons, birth decades, and the places mentioned. TagMe offsets drifted from the texts; each mention is moved to
the occurrence of its spot string nearest to its recorded start (decision 0006).
"""

import collections
import gzip
import hashlib
import json
import multiprocessing
import sys
import time
from pathlib import Path

from . import config, solr

LANGS = {"Deutsch": "German", "Hebräisch": "Hebrew", "Jiddisch": "Yiddish", "Englisch": "English",
         "Französisch": "French", "Russisch": "Russian", "Ungarisch": "Hungarian", "Spanisch": "Spanish",
         "Polnisch": "Polish", "Italienisch": "Italian", "Niederländisch": "Dutch", "Tschechisch": "Czech",
         "Ladino": "Ladino", "Latein": "Latin"}

TEXT_TYPE = {
    "name": "text_cm", "class": "solr.TextField", "positionIncrementGap": "100",
    "storeOffsetsWithPositions": True,
    "analyzer": {"tokenizer": {"class": "solr.StandardTokenizerFactory"},
                 "filters": [{"class": "solr.LowerCaseFilterFactory"},
                             {"class": "solr.ASCIIFoldingFilterFactory", "preserveOriginal": True}]},
}


def _f(name, type_, multi=False, stored=True, indexed=True, dv=None):
    f = {"name": name, "type": type_, "multiValued": multi, "stored": stored, "indexed": indexed}
    if dv is not None:
        f["docValues"] = dv
    return f


FIELDS = [
    _f("iri", "string"),
    _f("journal", "string", dv=True),
    _f("parent", "string", dv=True),
    _f("units", "string", multi=True, stored=False),
    _f("volume", "text_cm"), _f("issue", "text_cm"), _f("article", "text_cm"),
    _f("date", "pdate"),
    _f("year", "pint", dv=True), _f("decade", "pint", dv=True),
    _f("seq", "pint", dv=True), _f("pageno", "pint", dv=True),
    _f("label", "string", indexed=False, dv=False),
    _f("lang", "string", multi=True, dv=True),
    _f("ptype", "string", dv=True),
    _f("ocr", "pfloat", dv=True),
    _f("text", "text_cm"),
    _f("ep", "string", multi=True, dv=True),
    _f("ep_person", "string", multi=True, stored=False, dv=True),
    _f("ep_place", "string", multi=True, stored=False, dv=True),
    _f("ep_subject", "string", multi=True, stored=False, dv=True),
    _f("eclass", "string", multi=True, stored=False, dv=True),
    _f("occ", "string", multi=True, stored=False, dv=True),
    _f("bplace", "string", multi=True, stored=False, dv=True),
    _f("bdecade", "pint", multi=True, stored=False, dv=True),
    _f("n_ent", "pint", dv=True),
    _f("mentions", "string", indexed=False, dv=False),
    _f("refs", "string", multi=True, stored=False),
]

# shared with the worker processes (fork)
PAGES, CHAIN, ENT = {}, {}, {}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def align(text, spot, start, low=None):
    """The (start, end) of the occurrence of spot in text nearest to start, or None."""
    if not spot:
        return None
    best, i = None, text.find(spot)
    while i >= 0:
        if best is None or abs(i - start) < abs(best - start):
            best = i
        if i > start and best is not None and i - start > abs(best - start):
            break
        i = text.find(spot, i + 1)
    if best is None and low is not None:
        sl = spot.lower()
        i = low.find(sl)
        while i >= 0:
            if best is None or abs(i - start) < abs(best - start):
                best = i
            i = low.find(sl, i + 1)
    return None if best is None else (best, best + len(spot))


def chain(parent):
    """The ancestors of a node, nearest first, up to (not including) the journal."""
    out, n, seen = [], parent, set()
    while n and n in CHAIN and n not in seen:
        seen.add(n)
        out.append(n)
        n = CHAIN[n]
    return out


def build(d, stats):
    vlid = d["id"]
    doc = {"id": vlid, "journal": d["vlid_journal"], "text": d.get("text", "")}
    for src, dst in (("volume", "volume"), ("heft", "issue"), ("aufsatz", "article"), ("page_label", "label"),
                     ("parent_type", "ptype")):
        if d.get(src):
            doc[dst] = d[src]
    if d.get("dateIssued"):
        doc["date"] = d["dateIssued"]
        y = int(d["dateIssued"][:4])
        doc["year"], doc["decade"] = y, y // 10 * 10
    if "page" in d:
        doc["pageno"] = int(d["page"])
    if d.get("lang"):
        doc["lang"] = [LANGS.get(x.strip(), x.strip()) for x in d["lang"].split(";") if x.strip()]
    row = PAGES.get(vlid)
    if row is None:
        stats["no_rdf_page"] += 1
        doc["parent"] = d.get("vlid_parent", "")
        doc["units"] = [doc["parent"]] if doc["parent"] else []
        return doc
    iri, parent, seq, ocr, mentions = row
    doc["iri"] = iri
    if parent:
        doc["parent"] = parent
        doc["units"] = chain(parent)
    if seq:
        doc["seq"] = int(seq)
    if ocr:
        doc["ocr"] = float(ocr)
    if mentions:
        text = doc["text"]
        low = text.lower()
        if len(low) != len(text):
            low = None
        ms, eps, refs = [], set(), []
        for ep, start, end, spot, ref, rho in json.loads(mentions):
            pos = None
            if 0 <= start < end <= len(text) and text[start:end] == spot:
                pos = (start, end)
                stats["exact"] += 1
            else:
                pos = align(text, spot, start, low)
                stats["moved" if pos else "not_found"] += 1
            ms.append([ep, pos[0] if pos else -1, pos[1] if pos else -1, spot, ref])
            eps.add(ep)
            refs.append(str(ref))
        doc["mentions"] = json.dumps(ms, ensure_ascii=False, separators=(",", ":"))
        doc["ep"] = sorted(str(e) for e in eps)
        doc["refs"] = refs
        doc["n_ent"] = len(eps)
        cls, occ, bpl, bdec = set(), set(), set(), set()
        for e in eps:
            info = ENT.get(e)
            if not info:
                continue
            c, o, g, bd = info
            cls.add(c)
            doc.setdefault(f"ep_{c}", []).append(str(e)) if c in ("person", "place", "subject") else None
            occ.update(o)
            if g:
                bpl.add(g)
            if bd is not None:
                bdec.add(bd)
        for k, v in (("eclass", cls), ("occ", occ), ("bplace", bpl), ("bdecade", bdec)):
            if v:
                doc[k] = sorted(v)
    else:
        doc["n_ent"] = 0
    return doc


def index_part(args):
    core, part = args
    stats = collections.Counter()
    journals = {}
    batch, size = [], 0

    def flush():
        nonlocal batch, size
        if batch:
            solr.add(core, ("[" + ",".join(batch) + "]").encode())
            batch, size = [], 0

    with gzip.open(part, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            doc = build(d, stats)
            stats["docs"] += 1
            j = journals.setdefault(d["vlid_journal"], {"title": d.get("j_title", ""), "pages": 0})
            j["pages"] += 1
            s = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
            batch.append(s)
            size += len(s)
            if len(batch) >= 1000 or size > 8_000_000:
                flush()
    flush()
    return part.name, stats, journals


def setup_schema(core):
    types = solr.field_types(core)
    cmds = {("replace-field-type" if TEXT_TYPE["name"] in types else "add-field-type"): TEXT_TYPE}
    solr.schema(core, cmds)
    have = solr.fields(core)
    cmds = {}
    for f in FIELDS:
        cmds.setdefault("replace-field" if f["name"] in have else "add-field", []).append(f)
    solr.schema(core, cmds)
    solr.set_user_property(core, "update.autoCreateFields", "false")


def verify_bundle(bundle, manifest):
    for p in manifest["parts"]:
        h = hashlib.sha256()
        with open(bundle / p["file"], "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != p["sha256"]:
            sys.exit(f"checksum mismatch: {p['file']}")


def run(new, core=None, workers=3, verify=True, swap=True):
    core = core or config.CORE
    bundle = config.DATA / "inputs" / config.BUNDLE
    manifest = json.loads((bundle / "manifest.json").read_text("utf-8"))
    status = solr.cores()
    if new not in status:
        sys.exit(f"Solr core {new} does not exist: create it first (bin/index.sh does that)")
    if status[new].get("index", {}).get("numDocs", 0):
        sys.exit(f"Solr core {new} is not empty")
    t0 = time.time()
    if verify:
        verify_bundle(bundle, manifest)
        log("bundle checksums ok")

    with gzip.open(config.PREPARED / "pages.tsv.gz", "rt", encoding="utf-8") as f:
        for line in f:
            vlid, iri, parent, seq, ocr, mentions = line.rstrip("\n").split("\t")
            PAGES[vlid] = (iri, parent, seq, ocr, mentions)
    structure = json.loads((config.PREPARED / "structure.json").read_text("utf-8"))
    for nid, n in structure["nodes"].items():
        if n.get("p") and n["p"] not in structure["journals"]:
            CHAIN[nid] = n["p"]
        else:
            CHAIN[nid] = None
    ents = json.loads((config.PREPARED / "entities.json").read_text("utf-8"))["entities"]
    for k, e in ents.items():
        ENT[int(k)] = (e["cls"], e.get("occ", []), (e.get("bplace") or {}).get("gid"),
                       e["by"] // 10 * 10 if "by" in e and 1000 <= e["by"] <= 2030 else None)
    log("prepared data loaded:", len(PAGES), "pages,", len(ENT), "entities")

    setup_schema(new)
    log("schema set on", new)
    parts = [(new, bundle / p["file"]) for p in sorted(manifest["parts"], key=lambda p: -p["docs"])]
    total = collections.Counter()
    journals = {}
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(workers) as pool:
        for name, stats, js in pool.imap_unordered(index_part, parts):
            total.update(stats)
            for jid, j in js.items():
                journals.setdefault(jid, {"title": j["title"], "pages": 0})["pages"] += j["pages"]
            log(f"{name}: {stats['docs']} docs ({total['docs']} so far, {time.time() - t0:.0f} s)")
    solr.commit(new)
    n = solr.select(new, {"q": "*:*", "rows": 0})["response"]["numFound"]
    log("committed", n, "docs; mentions", dict(total))
    if n != manifest["docs"]:
        sys.exit(f"{new} has {n} documents, the manifest says {manifest['docs']}: not swapped")
    solr.optimize(new)                  # one segment: 6.8 GB instead of 13 (2026-10-14)
    log("merged into one segment")
    report = {"core": core, "bundle": config.BUNDLE, "docs": n, "seconds": round(time.time() - t0),
              "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "stats": dict(total)}
    (config.PREPARED / "bundle-journals.json").write_text(json.dumps(journals, ensure_ascii=False), "utf-8")
    (config.PREPARED / "index-report.json").write_text(json.dumps(report, indent=1), "utf-8")
    if swap:
        if core in solr.cores():
            solr.core_admin(action="SWAP", core=core, other=new)
            solr.core_admin(action="UNLOAD", core=new, deleteIndex="true", deleteDataDir="true",
                            deleteInstanceDir="true")
        else:
            solr.core_admin(action="RENAME", core=new, other=core)
        log(f"{core} swapped in")
    log(f"done in {time.time() - t0:.0f} s")
    return report
