"""A small streaming Turtle reader (standard library) for the files of the JudaicaLink dumps.

It covers what the dumps use: @prefix/PREFIX, IRIs, prefixed names, `a`, literals (short and long, with language
tag or datatype), numbers, booleans, and the `;` and `,` lists. No blank nodes and no collections (the dumps have
none; JudaicaLink convention). A literal is returned as Lit(value, lang, datatype); an IRI as a plain str.

    for s, p, o in triples("compact-memory-pages.ttl.gz"): ...
"""

import gzip
import re
from typing import NamedTuple

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD = "http://www.w3.org/2001/XMLSchema#"


class Lit(NamedTuple):
    value: str
    lang: str | None = None
    datatype: str | None = None


TOKEN = re.compile(r'''
    \s+ | \#[^\n]*
  | (?P<iri><[^>]*>)
  | (?P<lit>"""(?:[^"\\]|\\.|"(?!""))*"""|'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")
        (?:@(?P<lang>[A-Za-z0-9-]+)|\^\^(?P<dt><[^>]*>|[A-Za-z0-9_-]*:[^\s;,]*?(?=[\s;,]|\.(?:\s|$))))?
  | (?P<kw>@prefix|@base|PREFIX|BASE)\b
  | (?P<punct>[;,.\[\]()])
  | (?P<num>[+-]?(?:\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?))(?=[\s;,]|\.(?:\s|$))
  | (?P<a>a)(?=\s)
  | (?P<bool>true|false)(?=[\s;,.])
  | (?P<pn>[A-Za-z0-9_-]*:(?:[^\s;,"<>\\]|\\.)*?)(?=[\s;,]|\.(?:\s|$)|$)
''', re.S | re.X)
PREFIX_DECL = re.compile(r'\s*([A-Za-z0-9_-]*):\s*<([^>]*)>\s*\.?')
ESCAPES = re.compile(r'\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)', re.S)
SIMPLE = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def _unescape(s):
    if "\\" not in s:
        return s

    def rep(m):
        e = m.group(1)
        if e[0] in "uU":
            return chr(int(e[1:], 16))
        return SIMPLE.get(e, e)
    return ESCAPES.sub(rep, s)


def _open(path):
    path = str(path)
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def triples(path):
    """Yield (subject, predicate, object) from a Turtle file (.ttl or .ttl.gz)."""
    with _open(path) as f:
        data = f.read()
    prefixes = {}

    def expand(pn):
        p, l = pn.split(":", 1)
        return prefixes[p] + l.replace("\\", "")

    pos, n = 0, len(data)
    state, s, p = 0, None, None
    while pos < n:
        m = TOKEN.match(data, pos)
        if not m:
            raise ValueError(f"cannot read Turtle at {pos}: {data[pos:pos + 80]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind is None:
            continue
        if kind == "kw":
            if m.group("kw").lower().endswith("prefix"):
                d = PREFIX_DECL.match(data, pos)
                prefixes[d.group(1)] = d.group(2)
                pos = d.end()
            else:
                pos = data.index(">", pos) + 1
                if data[pos:pos + 2].strip().startswith("."):
                    pos = data.index(".", pos) + 1
            continue
        if kind == "punct":
            c = m.group("punct")
            if c == ".":
                state = 0
            elif c == ";":
                state = 1
            elif c == ",":
                state = 2
            else:
                raise ValueError(f"blank nodes and collections are not supported (at {pos})")
            continue
        if kind == "iri":
            t = m.group("iri")[1:-1]
        elif kind == "pn":
            t = expand(m.group("pn"))
        elif kind == "a":
            t = RDF_TYPE
        elif kind == "lit" or m.group("lit") is not None:
            raw = m.group("lit")
            q = 3 if raw.startswith(('"""', "'''")) else 1
            dt = m.group("dt")
            if dt:
                dt = dt[1:-1] if dt.startswith("<") else expand(dt)
            t = Lit(_unescape(raw[q:-q]), m.group("lang"), dt)
        elif kind == "num":
            v = m.group("num")
            t = Lit(v, None, XSD + ("integer" if re.fullmatch(r"[+-]?\d+", v) else
                                     "decimal" if "e" not in v.lower() else "double"))
        elif kind == "bool":
            t = Lit(m.group("bool"), None, XSD + "boolean")
        else:
            raise ValueError(kind)
        if state == 0:
            s, state = t, 1
        elif state == 1:
            p, state = t, 2
        else:
            yield s, p, t
            state = 3
