# 0002 What the showcase reads: the loaded versions, the full-text bundle, the page table

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

The graph data are published versions in the store; the full text is not public (the bundle made for the portal of
the FID, 2 GB). The store on the platform holds the versions loaded into Fuseki.

## Decision

- **Graph data:** the newest version under `/store/<slug>/` of compact-memory, cm-ocr-quality, cm-tagme, cm-entities, ep
  (and compact-memory-supp). The versions used are written to `prepared/versions.json` and shown on the start page.
- **Full text:** the bundle `fulltext-2026-10-05-v2` (846,500 pages; the same texts as the portal search), copied by
  hand to `/data/mannheim/showcases/compact-memory/inputs/`. The indexer checks its checksums against the manifest and
  refuses to swap in a core whose document count differs from the manifest.
- **Join:** bundle page = RDF page by VLID (the last segment of the page IRI). TagMe references point to page IRIs, some
  of them the 2021 IRIs; they are joined by VLID too. 894 VLIDs of TagMe (1,688 mentions) are not pages of the
  current version and are left out; one bundle page has no RDF record and is indexed without IRI.
- **Page table of the 2020 export** (`CM_Seiten_Metadaten.csv.gz` of compact-memory-supp), needed only to attribute dropped
  pages to journals in the dashboard: from the store if it is there, else from `inputs/compact-memory-supp/`. The store on
  the platform holds only the `-meta` of compact-memory-supp, so the file was copied there by hand.

## Consequences

- Rebuilding on a fresh VM needs the bundle and the page table copied into `inputs/` (README).
- A new version of compact-memory changes nothing in the code: `bin/index.sh` picks it up.
