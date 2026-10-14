"""HTML helpers: escaping, links, the page shell (platform kit and bar), small SVG charts.

Everything a visitor typed goes through esc(): nginx runs server-side includes on these pages, so a typed
<!--# … --> must never reach the HTML unescaped."""

import hashlib
import html
import urllib.parse
from pathlib import Path

from . import config

# the static files' version in their URLs, so that browsers fetch them again after a change
STATIC_VERSION = hashlib.sha256(b"".join(f.read_bytes() for f in sorted((Path(__file__).parent / "static").glob("*"))
                                         if f.is_file())).hexdigest()[:10]


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def u(path, **params):
    """A URL inside the showcase: u('/search', q='x', e=[1, 2])."""
    q = []
    for k, v in params.items():
        if v is None or v == "" or v == []:
            continue
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            q.append((k.rstrip("_"), str(x)))
    return config.BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")


def platform(iri):
    """The platform's view of a JudaicaLink IRI: the IRI with the host swapped (judaicalink-mannheim 0002)."""
    if iri.startswith(config.JL_DATA):
        return config.PLATFORM + "/" + iri[len(config.JL_DATA):]
    return iri


def ep_iri(n):
    return f"{config.JL_DATA}data/ep/{n}"


def cm_iri(local):
    return f"{config.JL_DATA}data/compact-memory/{local}"


def sparql_link(query, text="query"):
    href = config.SPARQL_EDITOR + "#" + urllib.parse.urlencode({"query": query, "endpoint": "/sparql"},
                                                               quote_via=urllib.parse.quote)
    return f'<a class="jl-query" href="{esc(href)}" title="The query behind this number">{esc(text)}</a>'


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


NAV = [("/", "Start"), ("/search", "Search"), ("/journals", "Journals"), ("/dashboard/", "Dashboard")]


def page(title, body, active=None, q="", wide=False, head="", description=None):
    nav = "".join(f'<a href="{config.BASE}{p}"{" aria-current=page" if p == active else ""}>{t}</a>'
                  for p, t in NAV)
    desc = description or ("Compact Memory: full-text and knowledge-graph search over 846,500 pages of Jewish "
                           "periodicals (1768–1938), digitised by the UB Frankfurt.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}{' · ' if title else ''}Compact Memory · JudaicaLink Mannheim</title>
<meta name="description" content="{esc(desc)}">
<link rel="stylesheet" href="/kit/1/jl.css">
<link rel="stylesheet" href="{config.BASE}/static/cm.css?v={STATIC_VERSION}">
{head.replace(".css\"", ".css?v=" + STATIC_VERSION + '"')}
</head>
<body>
<!--# include virtual="/kit/1/header.html" -->
<div class="cm-sub"><div class="cm-sub-in">
<a class="cm-brand" href="{config.BASE}/">Compact Memory</a>
<nav class="cm-nav" aria-label="Compact Memory">{nav}</nav>
<form class="cm-quick" action="{config.BASE}/search" role="search">
<input type="search" name="q" value="{esc(q)}" placeholder="Search the full text" aria-label="Search the full text">
<button type="submit" aria-label="Search">Search</button></form>
</div></div>
<main class="cm-main{' cm-wide' if wide else ''}">
{body}
</main>
<footer class="jl-footer cm-footer">
<p>Compact Memory was digitised by the <a href="https://sammlungen.ub.uni-frankfurt.de/cm">University Library
Frankfurt am Main</a>; images and viewer are theirs. The production full-text search is in the portal of the
<a href="{config.PRODUCTION}">FID Jewish Studies</a>. This is a showcase of the Mannheim development platform of
JudaicaLink (<a href="https://github.com/judaicalink/jlma-compact-memory">source</a>).</p>
</footer>
<script src="{config.BASE}/static/cm.js?v={STATIC_VERSION}" defer></script>
</body>
</html>
"""


def bars(series, href=None, label="Pages per year", unit="pages", first=None, last=None, mark=None):
    """A bar chart of (year, count) in HTML (flex bars, crisp at any width), one slot per year from first to
    last; bars link to href(year). mark: a set of years to emphasise."""
    data = {y: c for y, c in series if c}
    if not data:
        return '<p class="jl-meta">No dated pages.</p>'
    x0 = first if first is not None else min(data)
    x1 = last if last is not None else max(data)
    top = max(data.values())
    cells = []
    for y in range(x0, x1 + 1):
        c = data.get(y, 0)
        if not c:
            cells.append("<i></i>")
            continue
        h = max(1.5, c / top * 100)
        tip = f"{y}: {fmt(c)} {unit}"
        cls = ' class="on"' if mark and y in mark else ""
        if href:
            cells.append(f'<a{cls} href="{esc(href(y))}" style="--h:{h:.1f}%" title="{tip}" aria-label="{tip}"></a>')
        else:
            cells.append(f'<b{cls} style="--h:{h:.1f}%" title="{tip}"></b>')
    mid = (x0 + x1) // 2 if x1 - x0 > 8 else None
    axis = f'<span>{x0}</span>' + (f'<span>{mid}</span>' if mid else "") + f'<span>{x1}</span>'
    return (f'<figure class="cm-bars" aria-label="{esc(label)}"><div class="cm-bars-top">{fmt(top)}</div>'
            f'<div class="cm-bars-plot">{"".join(cells)}</div><div class="cm-bars-axis">{axis}</div></figure>')


def iiif(vlid, width=200):
    return config.IIIF.format(vlid=vlid, width=width)
