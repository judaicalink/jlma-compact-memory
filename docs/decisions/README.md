# Decisions about this showcase

One file per decision. All were made autonomously on 2026-10-14 while Kai was away and are to be reviewed with him.
Decisions about the platform are in judaicalink-mannheim, about the data in judaicalink-data.

| | Decision |
|---|---|
| [0001](0001-architecture.md) | One standard-library app with its jobs; Solr for the pages, the rest in memory; the join from the RDF files |
| [0002](0002-data-sources.md) | The loaded versions from the store, the full-text bundle and the page table in `inputs/`, joined by VLID |
| [0003](0003-solr-schema.md) | The Solr core: fields, text analysis without ICU (Hebrew and Yiddish: exact words), stored text for highlighting |
| [0004](0004-core-lifecycle.md) | A new core per build with `solr create` (own configset copy), checked, swapped in |
| [0005](0005-semantic-search.md) | Semantic search: entity pages mentioned on a page and facts about them as facets (occupation, birth place, birth decade, places) |
| [0006](0006-mention-offsets.md) | TagMe offsets moved to the nearest occurrence of the spot at index time |
| [0007](0007-urls-and-links.md) | Paths, links to the platform's IRI views, `resolve`, query links |
| [0008](0008-dashboard.md) | The dashboard: CM view of the data profile, graph figures from SPARQL with links |
| [0009](0009-page-images.md) | Page images from the UB Frankfurt's IIIF service, not copied |
| [0010](0010-look.md) | Platform kit, server-rendered pages, little JavaScript, escaping |
