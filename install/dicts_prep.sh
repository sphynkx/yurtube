#!/usr/bin/env bash
set -Eeuo pipefail

# ASCII ONLY
# Usage:
#   bash install/dicts_prep.sh             # default: create symlinks in tsearch_data
#   bash install/dicts_prep.sh --copy      # copy files instead of symlinks
#   CREATE_DB_DICTIONARIES=1 bash install/dicts_prep.sh   # also create ru_ispell/en_ispell in DB (requires PG* env)
#
# Requires:
#   - Packages: postgresql-contrib, postgresql-devel (pg_config), hunspell-ru (and optionally hunspell-en)
#   - Root permissions for writing to tsearch_data (script uses sudo)

MODE="link"  # link | copy
CREATE_DB="${CREATE_DB_DICTIONARIES:-0}"

if [[ "${1:-}" == "--copy" ]]; then
  MODE="copy"
fi

# 1) Locate tsearch_data
if command -v pg_config >/dev/null 2>&1; then
  TSDIR="$(pg_config --sharedir)/tsearch_data"
else
  if [[ -d /usr/share/pgsql/tsearch_data ]]; then
    TSDIR="/usr/share/pgsql/tsearch_data"
  elif [[ -d /usr/share/postgresql/tsearch_data ]]; then
    TSDIR="/usr/share/postgresql/tsearch_data"
  else
    echo "ERROR: tsearch_data not found. Install postgresql-devel (for pg_config) or create /usr/share/pgsql/tsearch_data"
    exit 1
  fi
fi
echo "tsearch_data: $TSDIR"
sudo install -d -m 0755 "$TSDIR"

# 2) Check unaccent.rules presence (from postgresql-contrib)
if [[ ! -f "$TSDIR/unaccent.rules" ]]; then
  echo "WARNING: $TSDIR/unaccent.rules is missing. Install postgresql-contrib."
fi

# 3) Source hunspell files
HUN="/usr/share/hunspell"
RU_AFF="$HUN/ru_RU.aff"
RU_DIC="$HUN/ru_RU.dic"
EN_AFF="$HUN/en_US.aff"
EN_DIC="$HUN/en_US.dic"

put_file() {
  local src="$1" dst="$2"
  if [[ "$MODE" == "link" ]]; then
    sudo ln -sf "$src" "$dst"
  else
    sudo install -m 0644 "$src" "$dst"
  fi
}

# 4) Place base ru_RU.* into tsearch_data
if [[ -f "$RU_AFF" && -f "$RU_DIC" ]]; then
  put_file "$RU_AFF" "$TSDIR/ru_RU.affix"
  put_file "$RU_DIC" "$TSDIR/ru_RU.dict"
  echo "Placed: ru_RU.affix, ru_RU.dict"
else
  echo "ERROR: $RU_AFF or $RU_DIC not found. Install hunspell-ru."
  exit 1
fi

# 5) Optional en_US.*
HAVE_EN=0
if [[ -f "$EN_AFF" && -f "$EN_DIC" ]]; then
  put_file "$EN_AFF" "$TSDIR/en_US.affix"
  put_file "$EN_DIC" "$TSDIR/en_US.dict"
  HAVE_EN=1
  echo "Placed: en_US.affix, en_US.dict"
else
  echo "NOTE: hunspell-en not found. Skipping English hunspell."
fi

# 6) Short aliases ru.* -> ru_RU.*
sudo ln -sf "$TSDIR/ru_RU.affix" "$TSDIR/ru.affix"
sudo ln -sf "$TSDIR/ru_RU.dict"  "$TSDIR/ru.dict"

# 7) Convert ru_RU.* to UTF-8 if needed -> ru_utf8.*
first_line="$(head -n 1 "$TSDIR/ru_RU.affix" || true)"
enc="UTF-8"
if echo "$first_line" | grep -qi 'KOI8'; then
  enc="KOI8-R"
fi

if [[ "$enc" != "UTF-8" ]]; then
  echo "Converting ru_RU.* from $enc to UTF-8..."
  sudo bash -lc "iconv -f $enc -t UTF-8 '$TSDIR/ru_RU.affix' | sed -E '1s/^SET .*/SET UTF-8/' > '$TSDIR/ru_utf8.affix'"
  sudo bash -lc "iconv -f $enc -t UTF-8 '$TSDIR/ru_RU.dict'  > '$TSDIR/ru_utf8.dict'"
  sudo chmod 0644 "$TSDIR/ru_utf8.affix" "$TSDIR/ru_utf8.dict"
else
  sudo install -m 0644 "$TSDIR/ru_RU.affix" "$TSDIR/ru_utf8.affix"
  sudo install -m 0644 "$TSDIR/ru_RU.dict"  "$TSDIR/ru_utf8.dict"
fi

# 8) English utf8 copies if present
if [[ $HAVE_EN -eq 1 ]]; then
  sudo install -m 0644 "$TSDIR/en_US.affix" "$TSDIR/en_utf8.affix"
  sudo install -m 0644 "$TSDIR/en_US.dict"  "$TSDIR/en_utf8.dict"
fi

echo "Summary:"
ls -l "$TSDIR" | grep -E 'unaccent\.rules|ru_(RU|utf8)|ru\.(affix|dict)|en_(US|utf8)' || true

# 9) Optional: create DB dictionaries if env set
if [[ "$CREATE_DB" == "1" ]]; then
  echo "Creating DB dictionaries via psql..."
  : "${PGDATABASE:?Set PGDATABASE}"; : "${PGUSER:?Set PGUSER}"
  # PGHOST/PGPORT/PGPASSWORD can be set as needed
  psql -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS unaccent;"
  psql -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
  psql -v ON_ERROR_STOP=1 -c "DROP TEXT SEARCH DICTIONARY IF EXISTS ru_ispell;"
  psql -v ON_ERROR_STOP=1 -c "CREATE TEXT SEARCH DICTIONARY ru_ispell (TEMPLATE=ispell, DictFile='ru_utf8', AffFile='ru_utf8');"
  if [[ -f "$TSDIR/en_utf8.affix" && -f "$TSDIR/en_utf8.dict" ]]; then
    psql -v ON_ERROR_STOP=1 -c "DROP TEXT SEARCH DICTIONARY IF EXISTS en_ispell;"
    psql -v ON_ERROR_STOP=1 -c "CREATE TEXT SEARCH DICTIONARY en_ispell (TEMPLATE=ispell, DictFile='en_utf8', AffFile='en_utf8');"
  fi
  echo "DB dictionaries created."
fi

echo "Done."