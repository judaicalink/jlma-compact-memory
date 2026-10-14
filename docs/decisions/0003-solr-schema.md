# 0003 The Solr core of the pages: fields and text analysis

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

Solr 9.10.1 of the platform, standalone, 4 GB heap. The ICU and language-specific analysers are in modules that the
platform's Solr does not load (enabling them would change the platform's Solr). The pages are mostly German (93%),
some Hebrew, Yiddish, English, French, Russian, Hungarian, Spanish; OCR from 1768 to 1938 with old spellings, long s,
broken words.

## Decision

- One document per page, id = VLID. Fields (Schema API, `update.autoCreateFields=false`): `iri`, `journal`, `parent`,
  `units` (all ancestor nodes, for issue and volume views), `volume`, `issue`, `article` (text), `date`, `year`,
  `decade`, `seq`, `pageno`, `label`, `lang` (English names), `ptype` (the unit type of the Visual Library), `ocr`,
  `text`, the entity fields of 0005, `mentions` (stored JSON, not indexed) and `refs` (TagMe reference numbers, for
  resolving them).
- **Text type `text_cm`:** StandardTokenizer, LowerCase, ASCIIFolding with `preserveOriginal`: "Müller" matches
  "Muller" and "Müller", long s and ligatures fold. No stemming (OCR and historical spelling make stemmers misfire;
  exact words are what researchers expect). Hebrew and Yiddish are tokenised by the Unicode rules of the
  StandardTokenizer (words split at spaces and punctuation, niqqud kept): exact-word search works, prefixes and
  inflected forms do not. ICU folding would be the next step if the platform enables the analysis-extras module.
- The text is stored with offsets in the postings (`storeOffsetsWithPositions`) for the unified highlighter. Queries:
  edismax over `text` and `article` (boost 2), all words required (`q.op=AND`), phrase boost.
- Size: 846,500 documents, 7.2 GB, built in 210 s with 3 workers.

## Consequences

- Searches take 20–150 ms on the test VM; the index needs about 7 GB of disk per copy (twice during a rebuild).
