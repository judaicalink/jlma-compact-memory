# 0001 One standard-library app with its jobs, Solr for the pages, the rest in memory

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

The showcase needs full-text search over 846,500 OCR pages (about 4.8 GB of text), search by the entities the pages
mention and their properties in the graph, page, journal and issue views, and a dashboard. The platform
(judaicalink-mannheim 0001) offers Fuseki and Solr on the Docker network, prefers static pages, and asks for
Python standard library only, pinned images and containers that publish on 127.0.0.1 only.

## Decision

- **One image, two roles.** `server.py` is the app (`http.server`, threads, port 8110, base path `JL_BASE`); `jobs.py`
  runs the jobs in the same image: `prepare` (RDF → prepared files), `index` (bundle + prepared → Solr), `dashboard`
  (static page), `check` (smoke test). No dependencies beyond Python 3.13.
- **Solr holds the pages** (one core, `cm_pages`): the text for search and highlighting, the metadata, the IRI, the
  entities each page mentions and the facets derived from them. Every view that lists pages asks Solr.
- **The app keeps the small things in memory**, read from `DATA/prepared/` at start (0.2 s, about 130 MB): journals,
  the tree of volumes, issues and articles (88,692 nodes), the 5,444 entity pages with their facts and an index for the
  autocomplete, the birth places. No database.
- **The bulk join is made from the files, not over SPARQL.** `prepare` reads the Turtle of the loaded versions
  (`/data/mannheim/store`, mounted read-only) with a small streaming reader (`cm/ttl.py`): 749,446 references, 846,499
  pages and the entity pages in about a minute, deterministic, independent of the endpoint's limits. SPARQL is used
  where a figure should be checkable: the dashboard and the "query" links of the views.
- **The dashboard is static**, written by its job into the data volume and served by the app.
- **Browser code is plain JavaScript** (autocomplete, table sort, dashboard charts); every page works without it except
  the autocomplete and the dashboard's charts.

## Consequences

- After new data versions are loaded: `bin/index.sh` (prepare + index, about 5 minutes) and `jobs.py dashboard`.
- The app restarts to read new prepared files (`bin/index.sh` does it).
- `prepare` needs about 4.5 GB of memory for a minute (the entity pages file is read twice).
