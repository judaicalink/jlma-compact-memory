"""Job `check`: request the main views of the running app and report status and time (a smoke test)."""

import time
import urllib.error
import urllib.request

PATHS = ["/", "/search?q=Zionismus", "/search?occ=Rabbi", "/search?e=1007316&from=1897&to=1904", "/entity/1007316",
         "/page/2658089?q=Breslau", "/journals", "/journal/2651273", "/issue/2651359", "/dashboard/",
         "/api/entities?q=herzl", "/resolve?iri=http://data.judaicalink.org/data/ep/1007316",
         "/resolve?iri=http://data.judaicalink.org/data/dbpedia/Theodor_Herzl",
         "/search?q=%3C!--%23echo%20var%3D%22DATE_LOCAL%22%20--%3E", "/health"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def run(base):
    opener = urllib.request.build_opener(NoRedirect)
    bad = 0
    for p in PATHS:
        t = time.time()
        try:
            with opener.open(base + p, timeout=60) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        ok = status in (200, 302) and b"<!--#echo" not in body
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {status} {time.time() - t:6.2f} s {len(body):8d} B  {p}")
    return 1 if bad else 0
