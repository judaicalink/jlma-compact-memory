#!/usr/bin/env python3
"""The jobs of the Compact Memory showcase (run in the app's image, see README.md):

    python3 jobs.py prepare                 RDF of the store -> DATA/prepared/ (about 2 minutes)
    python3 jobs.py index --new <core>      bundle + prepared -> Solr core <core>, swapped in as cm_pages
    python3 jobs.py dashboard               DATA/dashboard/index.html (SPARQL, the index and the bundle)
    python3 jobs.py check [--base URL]      requests a few pages of the running app
"""

import argparse
import sys

from cm import config


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="job", required=True)
    p = sub.add_parser("prepare", help="read the RDF of the loaded versions")
    p.add_argument("--store", default=str(config.STORE))
    p = sub.add_parser("index", help="build the Solr core of the pages")
    p.add_argument("--new", required=True, help="the empty core to build into (bin/index.sh creates it)")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--no-verify", action="store_true", help="skip the checksums of the bundle")
    p.add_argument("--no-swap", action="store_true", help="leave the new core as it is")
    p = sub.add_parser("dashboard", help="write the dashboard page")
    p.add_argument("--no-sparql", action="store_true", help="take the graph figures from the last run")
    p = sub.add_parser("check", help="smoke test against the running app")
    p.add_argument("--base", default=f"http://127.0.0.1:{config.PORT}{config.BASE}")
    a = ap.parse_args()
    if a.job == "prepare":
        from cm import prepare
        prepare.run(a.store)
    elif a.job == "index":
        from cm import index
        index.run(a.new, workers=a.workers, verify=not a.no_verify, swap=not a.no_swap)
    elif a.job == "dashboard":
        from cm import dashboard
        dashboard.run(sparql=not a.no_sparql)
    elif a.job == "check":
        from cm import check
        return check.run(a.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
