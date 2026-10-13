"""What the app keeps in memory: journals, the tree of volumes and issues, the 5,445 entities (with an index for
the autocomplete), birth places, and the versions of the data. All from DATA/prepared/ (jobs.py prepare/index)."""

import collections
import json
import re
import unicodedata

from . import config

ISO639 = {"ger": "German", "heb": "Hebrew", "yid": "Yiddish", "eng": "English", "fre": "French", "rus": "Russian",
          "hun": "Hungarian", "spa": "Spanish", "lad": "Ladino", "pol": "Polish", "ita": "Italian", "dut": "Dutch",
          "cze": "Czech", "lat": "Latin", "ara": "Arabic", "rum": "Romanian", "lit": "Lithuanian", "lav": "Latvian",
          "per": "Persian", "arc": "Aramaic", "mul": "several languages", "und": "undetermined"}
CLASS_NAMES = {"person": "Person", "place": "Place", "subject": "Subject", "work": "Work", "other": "Other"}


def fold(s):
    """Lower case without diacritics, for matching names (Müller = muller, Ḥayyim = hayyim)."""
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("ß", "ss")


WORD = re.compile(r"\w+", re.U)


class Data:
    def __init__(self, prepared=None):
        p = prepared or config.PREPARED
        self.ok = (p / "structure.json").exists() and (p / "entities.json").exists()
        if not self.ok:
            self.journals, self.nodes, self.entities, self.places, self.versions = {}, {}, {}, {}, {}
            self.children, self.tagme, self.report, self.corpus = {}, {}, {}, {}
            self._index = []
            return
        st = json.loads((p / "structure.json").read_text("utf-8"))
        self.corpus = st.get("corpus", {})
        self.journals = st["journals"]
        bj = p / "bundle-journals.json"
        if bj.exists():
            for jid, j in json.loads(bj.read_text("utf-8")).items():
                r = self.journals.setdefault(jid, {})
                r.setdefault("title", j["title"])
                r["bundlePages"] = j["pages"]
        for j in self.journals.values():
            j.setdefault("title", "(untitled)")
            j["langNames"] = [ISO639.get(c, c) for c in j.get("lang", [])]
        self.nodes = st["nodes"]
        self.children = collections.defaultdict(list)
        for nid, n in self.nodes.items():
            if n.get("p"):
                self.children[n["p"]].append(nid)
        for k, v in self.children.items():
            v.sort(key=lambda c: (self.nodes[c].get("d", ""), _num(self.nodes[c].get("l", "")), int(c)))
        e = json.loads((p / "entities.json").read_text("utf-8"))
        self.entities = {int(k): v for k, v in e["entities"].items()}
        self.places = e["birthplaces"]
        self.tagme = {t: n for n, x in self.entities.items() for t in x["tagme"]}
        vp = p / "versions.json"
        self.versions = json.loads(vp.read_text("utf-8")) if vp.exists() else {}
        rp = p / "index-report.json"
        self.report = json.loads(rp.read_text("utf-8")) if rp.exists() else {}
        self.occupations = collections.Counter(o for x in self.entities.values() for o in x.get("occ", []))
        # the autocomplete: every label and alternative label, folded
        self._index = []
        for n, x in self.entities.items():
            names = {x["label"], x["pref"], *x.get("alt", [])}
            for name in names:
                f = fold(name)
                self._index.append((f, WORD.findall(f), n, name))

    def pages_of(self, n):
        return self.entities[n].get("presence", {}).get("pageCount", 0)

    def suggest(self, q, limit=10):
        """Entities whose label words start with every word of q, best first."""
        fq = fold(q).strip()
        words = WORD.findall(fq)
        if not words:
            return []
        best = {}
        for f, fwords, n, name in self._index:
            if not all(any(w.startswith(t) for w in fwords) for t in words):
                continue
            score = (0 if f == fq else 1 if f.startswith(fq) else 2, -self.pages_of(n))
            if n not in best or score < best[n][0]:
                best[n] = (score, name)
        ranked = sorted(best.items(), key=lambda kv: (kv[1][0][0] > 1, kv[1][0][1], kv[1][0][0]))[:limit]
        out = []
        for n, (score, name) in ranked:
            x = self.entities[n]
            out.append({"ep": n, "label": x["label"], "match": name if name != x["label"] else None,
                        "cls": x["cls"], "dates": life(x), "pages": self.pages_of(n),
                        "occ": x.get("occ", [])[:3]})
        return out

    def chain(self, nid):
        """The node and its ancestors, journal last: [(id, node)…]."""
        out, seen = [], set()
        while nid and nid in self.nodes and nid not in seen:
            seen.add(nid)
            out.append((nid, self.nodes[nid]))
            nid = self.nodes[nid].get("p")
        return out

    def journal_of(self, nid):
        n = self.nodes.get(nid, {})
        return n.get("j") or next((x.get("p") for _, x in reversed(self.chain(nid)) if x.get("p") in self.journals),
                                  None)

    def place_name(self, gid):
        p = self.places.get(gid)
        return p["name"] if p else gid


def _num(label):
    m = re.match(r"\D*(\d+)", label or "")
    return int(m.group(1)) if m else 0


def life(x):
    b, d = x.get("born"), x.get("died")
    if not b and not d:
        return ""
    return f"{b or '?'}–{d or ''}".rstrip("–") if d else f"born {b}"
