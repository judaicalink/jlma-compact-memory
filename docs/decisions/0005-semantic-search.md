# 0005 Graph-based semantic search: entities on the page and facts about them, as facets

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

Kai chose a graph-based semantic search, no machine learning. TagMe (2021, dataset cm-tagme) found 749,446 mentions of
5,445 entities (DBpedia names) on 316,775 pages. Each of them is represented by exactly one entity page (ep, decision
0022 of judaicalink-data); two TagMe entities share one page, so there are 5,444 entity pages: 4,127 persons, 1,251
places, 66 subjects. The entity pages bring together life dates, occupations, birth places (geonames), links.

## Decision

- **Per page the index stores** the entity-page numbers mentioned (`ep`, split by class into `ep_person`, `ep_place`,
  `ep_subject`), their classes (`eclass`), and derived facets of the mentioned persons: occupations (`occ`, the labels
  of `jl:occupationURI`), birth places (`bplace`, geonames ids from `jl:birthLocationURI`), birth decades (`bdecade`).
- **Filters:** entities (`e`), occupations (`occ`), birth places (`bp`), places mentioned (`pl`), birth decades (`bd`) combine
  with AND (each selected value must hold); journal, language, page type and class with OR within the facet (the facet
  keeps its other counts). All combine with the full-text query and the year range.
- **Labels:** an entity is shown by its Wikidata label (en, else de, from cm-entities), else its DBpedia name; the
  autocomplete matches every label and alternative label of the entity page, folded (case, diacritics), word prefixes,
  ranked by pages. A birth place is named by the place entity page with that geonames id (`owl:sameAs` sws.geonames.org),
  else by the most frequent `jl:birthLocation` literal.
- **The facts are about the entities, not the mention:** "mentions a person with occupation Rabbi and a person born in
  Posen" can be two persons. Said on the start page; per-person combinations would need nested documents.
- Occupation labels are the local names of the occupation IRIs as they are: mixed German and English
  (Schriftsteller, writer) — a mapping belongs into the data (judaicalink-data), not here.

## Consequences

- New facts on entity pages reach the search with the next `bin/index.sh`.
- Mentions are TagMe's, unchecked; some are wrong (e.g. "Babli" as a person). The views say so.
