# 0006 TagMe offsets: moved to the nearest occurrence of the spot, at index time

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

TagMe ran on the texts of 2021; the bundle's texts differ slightly, so `jl:hasStart`/`jl:hasEnd` drifted. Of the
747,758 mentions on indexed pages, only 200,822 (27%) still sit exactly on their spot string.

## Decision

At index time each mention is placed at the occurrence of its spot string nearest to its recorded start (case
sensitive first, then case-insensitive); the corrected positions are stored with the page (`mentions`). Result:
545,447 moved, 1,489 (0.2%) not found; those are listed with the page's entities but not marked in the text.

## Consequences

- The page view marks mentions without searching at request time. The published data stay as they are; a corrected
  complementary dataset of offsets could be made from the same rule (judaicalink-data) if wanted.
