SET search_path TO public;

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- FTS (simple) on title + description
CREATE INDEX IF NOT EXISTS videos_fts_simple_idx ON videos
USING GIN (
  to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''))
);

-- FTS (russian) on title + description
CREATE INDEX IF NOT EXISTS videos_fts_russian_idx ON videos
USING GIN (
  to_tsvector('russian', coalesce(title,'') || ' ' || coalesce(description,''))
);

-- Trigram for author search by username
CREATE INDEX IF NOT EXISTS users_username_trgm ON users
USING GIN (username gin_trgm_ops);

-- NEW: Trigram for fuzzy title and description
CREATE INDEX IF NOT EXISTS videos_title_trgm ON videos
USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS videos_description_trgm ON videos
USING GIN (description gin_trgm_ops);