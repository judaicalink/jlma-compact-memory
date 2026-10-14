# 0007 Paths of the showcase, links to the platform, and resolve

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

The platform shows a JudaicaLink IRI at the same path on its host (judaicalink-mannheim 0002) and links records of
the showcase's datasets to `/compact-memory/resolve?iri=…` (registry, decision 0007 there), from entity pages with the
entity-page IRI.

## Decision

- Paths under `/compact-memory`: `/` start, `/search`, `/entity/<ep number>`, `/page/<VLID>`, `/journals`,
  `/journal/<VLID>`, `/issue/<VLID>` (any node of the tree: volume, issue, article, other unit), `/dashboard/`,
  `/resolve?iri=`, `/api/entities?q=` (autocomplete, JSON), `/health`, `/static/…`. The VLID is the identifier of the
  Visual Library, stable and short; the IRIs are shown and linked on each view.
- Every JudaicaLink IRI is linked by the platform rule (`/data/ep/1007316`, `/data/compact-memory/…`, `/datasets/…`);
  the showcase builds no generic resource views, only its entity view (Compact Memory's angle on an entity).
- `resolve` redirects (302) to the showcase's view of: pages (current and 2021 IRIs, by VLID), journals, volumes,
  issues, articles, `data/ep/<n>` and `data/dbpedia/<X>` of the TagMe entities, `data/cm-entities/presence/…`, TagMe
  references `data/cm-tagme/<n>` (the page, with the mention marked), `data/compact-memory/corpus` (start page) and the
  four dataset IRIs (dashboard); anything else is 404. Hosts data. and mannheim.judaicalink.org are both accepted.
- Numbers from the graph link to their query in the platform's editor: `/sparql/#query=…&endpoint=%2Fsparql`.

## Consequences

- Links stay valid as long as VLIDs and entity-page numbers do (entity pages are never reused, judaicalink-data 0022).
