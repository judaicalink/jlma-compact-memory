"""A small Solr client (standard library)."""

import json
import urllib.error
import urllib.parse
import urllib.request

from . import config


class SolrError(Exception):
    pass


def _req(path, data=None, params=None, timeout=120, raw=None, ctype="application/json"):
    url = f"{config.SOLR}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    body = raw if raw is not None else (None if data is None else json.dumps(data).encode())
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("msg", "")
        except Exception:
            msg = ""
        raise SolrError(f"{e.code} {path}: {msg}") from None


def cores():
    return _req("admin/cores", params={"action": "STATUS", "wt": "json"})["status"]


def core_admin(**params):
    return _req("admin/cores", params={**params, "wt": "json"}, timeout=600)


def schema(core, commands):
    return _req(f"{core}/schema", commands)


def fields(core):
    return {f["name"] for f in _req(f"{core}/schema/fields")["fields"]}


def field_types(core):
    return {t["name"] for t in _req(f"{core}/schema/fieldtypes")["fieldTypes"]}


def set_user_property(core, name, value):
    return _req(f"{core}/config", {"set-user-property": {name: value}})


def add(core, docs_json_bytes):
    return _req(f"{core}/update", raw=docs_json_bytes, params={"wt": "json"}, timeout=600)


def commit(core):
    return _req(f"{core}/update", {"commit": {}}, timeout=3600)


def optimize(core):
    """Merge the index into one segment: smaller and faster to search; for a core that is built once and only read."""
    return _req(f"{core}/update", {"optimize": {"maxSegments": 1, "waitSearcher": True}}, timeout=7200)


def select(core, params, timeout=30):
    p = dict(params)
    p.setdefault("wt", "json")
    body = urllib.parse.urlencode(p, doseq=True).encode()
    return _req(f"{core}/select", raw=body, timeout=timeout, ctype="application/x-www-form-urlencoded")


def quote(v):
    """A value as a Solr term query term (for fq=field:<value>)."""
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
