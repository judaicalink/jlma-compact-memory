"""A SPARQL client (standard library): SELECT queries against the platform's internal endpoint."""

import json
import urllib.parse
import urllib.request

from . import config


def select(query, timeout=600):
    """The bindings of a SELECT query as a list of dicts {variable: value (str)}."""
    body = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(config.SPARQL, data=body, headers={
        "Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "jlma-compact-memory (JudaicaLink showcase)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.load(r)
    return [{k: v["value"] for k, v in b.items()} for b in res["results"]["bindings"]]
