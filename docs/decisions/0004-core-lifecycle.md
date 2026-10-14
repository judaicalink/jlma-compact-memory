# 0004 A new core per build, made by `solr create`, swapped in

Status: accepted (made autonomously 2026-10-14, to be reviewed with Kai) · Date: 2026-10-14

## Context

Rebuilding must not leave searches on a half-built index. Tested on the platform's Solr (2026-10-14): a core created
over the CoreAdmin API with `configSet=_default` shares the configset directory, and Schema API changes on it are
written into the shared `/var/solr/data/configsets/_default/conf/managed-schema.xml` (they would show up in every
later core made from `_default`, including the platform's own). A core also keeps its instance directory when it is
swapped or renamed, so a fixed name like `<core>_new` collides on the next build.

## Decision

- `bin/index.sh` (on the host) creates the build core with `docker exec <solr> solr create -c cm_pages_b<timestamp>`,
  which copies `_default` into the core's own directory, so this showcase's schema stays in its core.
- `jobs.py index --new <core>` sets the schema, loads, commits, checks the count against the manifest, then SWAPs with
  `cm_pages` (RENAME on the first build) and unloads the old core with its directories. On failure the new core is dropped
  and `cm_pages` stays as it was.

## Consequences

- Building needs docker on the host (for `solr create`); the job itself only talks HTTP.
- To be told to the platform: CoreAdmin `configSet=_default` plus Schema API changes the shared configset.
