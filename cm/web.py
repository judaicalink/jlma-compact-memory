"""The HTTP server of the showcase (standard library). Serves under config.BASE (nginx passes the full path on)."""

import json
import mimetypes
import re
import sys
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, solr, views
from .data import Data
from .html import esc, u

STATIC = Path(__file__).parent / "static"
D = None


def load():
    global D
    t = time.time()
    D = Data()
    print(f"data loaded in {time.time() - t:.1f} s: {len(D.entities)} entities, {len(D.journals)} journals, "
          f"{len(D.nodes)} nodes", file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------------------------- resolve

CM = config.JL_DATA + "data/compact-memory/"
IRI_RE = re.compile(r"^https?://(?:data|mannheim)\.judaicalink\.org/(.*)$")


def resolve(iri):
    """The showcase's own view of a JudaicaLink IRI, or None."""
    m = IRI_RE.match(iri.strip())
    if not m:
        return None
    path = urllib.parse.unquote(m.group(1)).split("#")[0].rstrip("/")
    if path.startswith("data/compact-memory/"):
        loc = path[len("data/compact-memory/"):]
        if loc == "corpus":
            return u("/")
        if "--" in loc:
            vlid = loc.rsplit("-", 1)[-1]
            if vlid.isdigit() and exists(f"id:{solr.quote(vlid)}"):
                return u(f"/page/{vlid}")
            return None
        if loc in D.journals:
            return u(f"/journal/{loc}")
        if loc in D.nodes:
            return u(f"/issue/{loc}")
        return None
    if m2 := re.fullmatch(r"data/ep/(\d+)", path):
        n = int(m2.group(1))
        return u(f"/entity/{n}") if n in D.entities else None
    if path.startswith("data/dbpedia/"):
        n = D.tagme.get(path[len("data/dbpedia/"):])
        return u(f"/entity/{n}") if n else None
    if path.startswith("data/cm-entities/presence/dbpedia/"):
        n = D.tagme.get(path[len("data/cm-entities/presence/dbpedia/"):])
        return u(f"/entity/{n}") if n else None
    if m2 := re.fullmatch(r"data/cm-tagme/(\d+)", path):
        r = solr.select(config.CORE, {"q": f"refs:{solr.quote(m2.group(1))}", "fl": "id,mentions", "rows": 1})
        docs = r["response"]["docs"]
        if docs:
            ms = json.loads(docs[0].get("mentions") or "[]")
            ep = next((x[0] for x in ms if str(x[4]) == m2.group(1)), None)
            return u(f"/page/{docs[0]['id']}", e=ep) + (f"#m{ep}" if ep else "")
        return None
    if path in ("datasets/compact-memory", "datasets/cm-tagme", "datasets/cm-entities", "datasets/cm-ocr-quality"):
        return u("/dashboard/")
    return None


def exists(q):
    return solr.select(config.CORE, {"q": q, "rows": 0})["response"]["numFound"] > 0


# ------------------------------------------------------------------------------------------------- handler

ROUTES = [
    (re.compile(r"/"), lambda m, p: views.home(D)),
    (re.compile(r"/search"), lambda m, p: views.search_view(D, p)),
    (re.compile(r"/entity/(\d+)"), lambda m, p: views.entity_view(D, int(m.group(1)))),
    (re.compile(r"/page/(\d+)"), lambda m, p: views.page_view(D, m.group(1), p)),
    (re.compile(r"/journals"), lambda m, p: views.journals_view(D)),
    (re.compile(r"/journal/(\d+)"), lambda m, p: views.journal_view(D, m.group(1))),
    (re.compile(r"/issue/(\d+)"), lambda m, p: views.issue_view(D, m.group(1), p)),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "jlma-compact-memory"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send(self, status, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def redirect(self, location, status=302):
        self.send(status, f'<a href="{esc(location)}">{esc(location)}</a>', headers={"Location": location})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self.route()
        except views.NotFound:
            self.send(*views.not_found())
        except solr.SolrError as e:
            traceback.print_exc()
            self.send(503, views.page("Unavailable", f"<h1>The index is not available</h1><p>{esc(e)}</p>"))
        except (ConnectionError, OSError) as e:
            traceback.print_exc()
            self.send(503, views.page("Unavailable", "<h1>The index is not available</h1>"
                                      "<p>The search index cannot be reached at the moment. Please try again later.</p>"))
        except Exception:
            traceback.print_exc()
            self.send(500, views.page("Error", "<h1>Something went wrong</h1><p>The error was logged.</p>"))

    def route(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        params = urllib.parse.parse_qs(url.query, keep_blank_values=False)
        base = config.BASE
        if path == base:
            return self.redirect(base + "/", 301)
        if base and not path.startswith(base + "/"):
            return self.send(*views.not_found())
        path = path[len(base):] or "/"
        if path == "/health":
            ok = D.ok and exists("*:*")
            return self.send(200 if ok else 503, json.dumps({"ok": ok, "entities": len(D.entities)}),
                             "application/json")
        if path.startswith("/static/"):
            return self.static(STATIC, path[len("/static/"):], cache=86400)
        if path == "/dashboard":
            return self.redirect(base + "/dashboard/", 301)
        if path.startswith("/dashboard/"):
            name = path[len("/dashboard/"):] or "index.html"
            return self.static(config.DASHBOARD, name, cache=600, missing="The dashboard has not been made yet "
                               "(jobs.py dashboard).")
        if path == "/resolve":
            iri = (params.get("iri") or [""])[0]
            target = resolve(iri) if iri else None
            if target:
                return self.redirect(target)
            return self.send(404, views.page("Not known", f"<h1>Not known here</h1><p>This showcase has no view of "
                                             f"<code>{esc(iri)}</code>.</p>"))
        if path == "/api/entities":
            q = (params.get("q") or [""])[0][:100]
            body = json.dumps(D.suggest(q, limit=12), ensure_ascii=True).replace("<", "\\u003c")
            return self.send(200, body, "application/json", {"Cache-Control": "max-age=3600"})
        for rx, fn in ROUTES:
            m = rx.fullmatch(path)
            if m:
                status, body = fn(m, params)
                return self.send(status, body)
        self.send(*views.not_found())

    def static(self, root, name, cache=0, missing="Not found."):
        root = root.resolve()
        f = (root / name).resolve()
        if root not in f.parents and f != root or not f.is_file():
            return self.send(*views.not_found(missing))
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send(200, f.read_bytes(), ctype, {"Cache-Control": f"max-age={cache}"})


def main():
    load()
    srv = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    srv.daemon_threads = True
    print(f"listening on :{config.PORT}{config.BASE}/", file=sys.stderr, flush=True)
    srv.serve_forever()
