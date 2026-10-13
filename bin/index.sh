#!/bin/sh
# Build the Solr core of the pages, on the host of the platform (needs docker). Run in the repository:
#   bin/index.sh             prepare (RDF -> prepared data) and index (bundle -> Solr), then swap in
#   bin/index.sh --no-prepare
# The new core is made with `solr create` inside the Solr container, which copies the _default configset into the
# core's own directory, so that the Schema API changes of this showcase stay in its core (decision 0004).
set -eu
cd "$(dirname "$0")/.."
PREPARE=1
[ "${1:-}" = "--no-prepare" ] && PREPARE=0
SOLR=$(docker ps -q --filter label=com.docker.compose.project=judaicalink --filter label=com.docker.compose.service=solr)
[ -n "$SOLR" ] || { echo "the Solr container of the platform is not running" >&2; exit 1; }
NEW="cm_pages_b$(date +%Y%m%d%H%M)"
docker compose build -q app
if [ $PREPARE = 1 ]; then
  docker compose run --rm --no-deps app python3 jobs.py prepare
fi
docker exec "$SOLR" solr create -c "$NEW" >/dev/null
echo "created core $NEW"
if ! docker compose run --rm --no-deps app python3 jobs.py index --new "$NEW"; then
  echo "indexing failed; dropping $NEW" >&2
  curl -s "http://127.0.0.1:8983/solr/admin/cores?action=UNLOAD&core=$NEW&deleteInstanceDir=true" >/dev/null
  exit 1
fi
docker compose restart app            # the app reads the prepared data at start
