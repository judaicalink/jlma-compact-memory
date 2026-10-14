# 0009 Page images from the IIIF service of the UB Frankfurt, not copied

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

The scans belong to the UB Frankfurt and are served by their Visual Library with a IIIF Image API.

## Decision

Thumbnails (`/full/200,/0/default.jpg`) and page images (`/full/1000,/0/default.jpg`) are loaded by the browser from
`sammlungen.ub.uni-frankfurt.de/i3f/v20/<VLID>/…`, lazily; every page links to the UB's page viewer. Nothing is cached
or copied here. The footer credits the UB Frankfurt and points to the production search of the FID portal.

## Consequences

- If the UB service is down, the views still work, without images.
