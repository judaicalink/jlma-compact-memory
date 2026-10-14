# 0008 The dashboard: the CM view of the data profile, now from the graph where possible

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

The workspace dashboard (`dashboard/`) has a Compact Memory view built from the bundle with its own OCR estimate. Since
then the OCR estimate has been published (cm-ocr-quality) and the journals have their own records
(compact-memory-journals).

## Decision

- `jobs.py dashboard` writes `/data/dashboard/index.html` (the platform shell, kit fonts and colours, no external fonts;
  charts in plain SVG): the sections of the old view (over time, journals with heatmap, table and detail, contents,
  OCR quality, data issues) plus **Compact Memory in the graph** (pages, journals, mentions, entities and their classes,
  share of pages with a mention per year, entities on most pages, journals by linked share).
- **From the graph** (SPARQL on the internal endpoint, 11 queries, about 45 s; each figure links to its query; the
  slowest takes 12 s, within the public endpoint's 120 s): all figures of the graph section, the OCR distribution and
  the OCR per journal. **From the bundle** (one pass, about 40 s): pages, words and languages per year and journal,
  metadata coverage, excerpts. **From both:** OCR per year (page shares of cm-ocr-quality by the bundle's dates).
- Dropped pages per journal come from the bundle's `dropped.tsv.gz` and the page table (0002).

## Consequences

- Run after each load of new versions; `--no-sparql` reuses the last graph figures when only the layout changed.
