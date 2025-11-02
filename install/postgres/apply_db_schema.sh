#!/usr/bin/env bash
set -Eeuo pipefail

# ASCII ONLY
# Usage:
#   export PGHOST=127.0.0.1
#   export PGPORT=5432
#   export PGDATABASE=yt_db
#   export PGUSER=yt_user
#   export PGPASSWORD='SECRET'
#   bash scripts/apply_db_schema.sh
#
# The script applies DDL in order and rebuilds the FTS index.

##: "${PGDATABASE:?Set PGDATABASE}"
##: "${PGUSER:?Set PGUSER}"

PGHOST=127.0.0.1
PGDATABASE=yt_db
PGUSER=yt_user

psql_base=(psql -h"$PGHOST" -U"$PGUSER" -d"$PGDATABASE" -v ON_ERROR_STOP=1)

echo "[1/4] fts_config.sql"
"${psql_base[@]}" -f install/postgres/ddl/fts_config.sql

echo "[2/4] videos_norm_fts.sql"
"${psql_base[@]}" -f install/postgres/ddl/videos_norm_fts.sql

echo "[3/4] videos_fuzzy_norm.sql"
"${psql_base[@]}" -f install/postgres/ddl/videos_fuzzy_norm.sql

# Optional legacy file if you still keep it
if [[ -f install/postgres/ddl/videos_fts.sql ]]; then
  echo "[4/4] videos_fts.sql"
  "${psql_base[@]}" -f install/postgres/ddl/videos_fts.sql
fi

echo "[Rebuild] FTS index for yt_multi"
"${psql_base[@]}" -c "DROP INDEX IF EXISTS videos_fts_yt_multi_idx;"
"${psql_base[@]}" -c "CREATE INDEX videos_fts_yt_multi_idx ON videos USING GIN (to_tsvector('yt_multi', coalesce(title_norm,'') || ' ' || coalesce(description_norm,'')));"

echo "[ANALYZE] videos"
"${psql_base[@]}" -c "ANALYZE videos;"

echo "Done."