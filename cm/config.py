"""Settings, from the environment (compose.yml sets them; the defaults suit a run inside the container)."""

import os
from pathlib import Path

BASE = os.environ.get("JL_BASE", "/compact-memory").rstrip("/")      # the path nginx passes on unchanged
PORT = int(os.environ.get("JL_PORT", "8110"))
SOLR = os.environ.get("JL_SOLR", "http://solr:8983/solr").rstrip("/")
SPARQL = os.environ.get("JL_SPARQL", "http://fuseki:3030/internal/query")
CORE = os.environ.get("CM_CORE", "cm_pages")                          # the Solr core of the pages
DATA = Path(os.environ.get("CM_DATA", "/data"))                       # the showcase's volume
STORE = Path(os.environ.get("CM_STORE", "/store"))                    # the files of the loaded versions, read-only
BUNDLE = os.environ.get("CM_BUNDLE", "fulltext-2026-10-05-v2")        # under DATA/inputs/

PREPARED = DATA / "prepared"        # made by `jobs.py prepare` from the RDF of the store
DASHBOARD = DATA / "dashboard"      # made by `jobs.py dashboard`

# what the platform shows a JudaicaLink IRI at: the IRI with the host swapped (judaicalink-mannheim 0002)
JL_DATA = "http://data.judaicalink.org/"
PLATFORM = os.environ.get("JL_PLATFORM", "")                          # "" = same host
SPARQL_EDITOR = PLATFORM + "/sparql/"

# the datasets this showcase reads (slug -> files), newest version under STORE/<slug>/
DATASETS = {
    "compact-memory": ["compact-memory-journals.ttl.gz", "compact-memory-pages.ttl.gz"],
    "cm-ocr-quality": ["cm-ocr-quality.ttl.gz"],
    "cm-tagme": ["cm_tagme_references.ttl.gz", "cm_tagme_resources.ttl.gz"],
    "cm-entities": ["cm-entities-presence.ttl.gz", "cm-entities-wikidata.ttl.gz"],
    "ep": ["ep.ttl.gz"],
    "compact-memory-supp": ["CM_Seiten_Metadaten.csv.gz"],
}

IIIF = "https://sammlungen.ub.uni-frankfurt.de/i3f/v20/{vlid}/full/{width},/0/default.jpg"
UB_PAGE = "https://sammlungen.ub.uni-frankfurt.de/cm/periodical/pageview/{vlid}"
UB_TITLE = "https://sammlungen.ub.uni-frankfurt.de/cm/periodical/titleinfo/{vlid}"
PRODUCTION = "https://www.jewishstudies.de/en/judaicalink/"
