# jlma-compact-memory

The Compact Memory showcase of [mannheim.judaicalink.org](https://mannheim.judaicalink.org/compact-memory/), the
Mannheim development platform of JudaicaLink.

Compact Memory is the collection of Jewish periodicals of the German-speaking countries digitised by the University
Library Frankfurt am Main: 846,500 OCR pages of 309 journals, mostly 1768–1938. The showcase offers:

- **Full-text search** (Solr): highlighted snippets, facets for journal, language, unit type and year (a clickable chart
  of pages per year), sorting by relevance or date.
- **Graph-based semantic search**: find pages by the entities they mention (TagMe, 2021; each entity represented by a
  JudaicaLink entity page) and by what the graph knows about them: "mentions a person with occupation Rabbi", "… born
  in Vienna", "… born in the 1810s", "mentions the place Breslau". Combinable with each other and with the full text.
  Entity autocomplete over all labels of the 5,444 entity pages.
- **Entity view** (`/entity/<n>`): facts, presence over time, journals, co-mentioned entities, pages; link to the
  platform's entity page `/data/ep/<n>`.
- **Page view** (`/page/<VLID>`): metadata, OCR quality, the scan (IIIF of the UB Frankfurt), the OCR text with the
  query and the entity mentions marked, previous and next page, links to issue, journal and the page's IRI.
- **Journals** (`/journals`, `/journal/<VLID>`) and **issues** (`/issue/<VLID>`, any volume, issue or article: its pages
  as thumbnails).
- **Dashboard** (`/dashboard/`): the collection in figures, and Compact Memory in the graph; every number from the
  graph links to its SPARQL query.
- **`/resolve?iri=<IRI>`**: a redirect to the showcase's view of a JudaicaLink IRI it knows (pages, issues, volumes,
  journals, entity pages and TagMe entities, TagMe references), else 404. Used by the platform's resource views.

Decisions: [`docs/decisions/`](docs/decisions/). Python standard library only, plain JavaScript, no external fonts or
CDNs.

## Layout

| Path | What |
|---|---|
| `server.py` | the app (`cm/web.py`): listens on 0.0.0.0:8110, serves under `JL_BASE` (`/compact-memory`) |
| `jobs.py` | the jobs: `prepare`, `index`, `dashboard`, `check` |
| `cm/prepare.py` | RDF of the store → `prepared/` (versions, structure, entities, per-page join) |
| `cm/index.py` | bundle + prepared → Solr core (schema, mention offsets, facets) |
| `cm/dashboard.py`, `cm/dashboard.html` | the dashboard job and its page |
| `cm/search.py`, `cm/views.py`, `cm/html.py`, `cm/data.py` | search, views, page shell, in-memory data |
| `cm/ttl.py`, `cm/solr.py`, `cm/sparql.py` | Turtle reader, Solr and SPARQL clients |
| `cm/static/` | CSS and JavaScript |
| `bin/index.sh` | builds the index on the host (creates the core inside the Solr container, runs the jobs) |
| `compose.yml`, `Dockerfile` | the container (`python:3.13.16-slim-trixie`, read-only, 127.0.0.1:8110) |

## Data

The showcase's volume is `/data/mannheim/showcases/compact-memory` (mounted at `/data`):

```
inputs/fulltext-2026-10-05-v2/        the full-text bundle (not public; copy by hand)
inputs/compact-memory-supp/CM_Seiten_Metadaten.csv.gz   the page table, if the store does not have it
prepared/                             written by jobs.py prepare and index
dashboard/                            written by jobs.py dashboard
```

The RDF comes from the platform's store `/data/mannheim/store` (mounted read-only at `/store`), the newest version of
compact-memory, cm-ocr-quality, cm-tagme, cm-entities, ep and compact-memory-supp. Services on the Docker network
`judaicalink`: Solr (`http://solr:8983/solr`, core `cm_pages`) and Fuseki (`http://fuseki:3030/internal/query`).

## Setting up on the platform

```sh
git clone https://github.com/judaicalink/jlma-compact-memory /data/mannheim/src/jlma-compact-memory
mkdir -p /data/mannheim/showcases/compact-memory/inputs
# copy the bundle (and, if the store lacks it, the page table) into inputs/, e.g. from the Mac:
#   limactl copy -r ~/lokal/judaicalink/inputs/compact-memory/fulltext-2026-10-05-v2 mannheim:/data/mannheim/showcases/compact-memory/inputs/
cd /data/mannheim/src/jlma-compact-memory
docker compose up -d --build                                      # the app
bin/index.sh                                                      # prepare + index, about 5 minutes
docker compose run --rm app python3 jobs.py dashboard             # about 1.5 minutes
docker compose exec app python3 jobs.py check                     # smoke test
```

The registry entry (`site/data/showcases.toml` of judaicalink-mannheim) has `path = "compact-memory"`, `port = 8110`;
nginx passes `/compact-memory/` to 127.0.0.1:8110 with SSI on.

After new data versions are loaded on the platform: `bin/index.sh` and the dashboard job again. The user and group
the container runs as (owner of the data directory) are `CM_UID`/`CM_GID` (default 501:1000).

## Running locally without the platform

Any Python ≥ 3.11, a Solr with a core `cm_pages` built as above, and:

```sh
CM_DATA=/path/to/data JL_SOLR=http://localhost:8983/solr JL_SPARQL=http://localhost:3030/internal/query python3 server.py
```

Without nginx, the platform bar is an HTML comment and `/kit/1/jl.css` is missing; the pages still work.
