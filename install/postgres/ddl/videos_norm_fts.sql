SET search_path TO public;

-- Normalized columns: lower + translate Ё/ё -> Е/е
ALTER TABLE videos
  ADD COLUMN IF NOT EXISTS title_norm text
    GENERATED ALWAYS AS ( lower( translate(coalesce(title,''), 'Ёё', 'Ее') ) ) STORED,
  ADD COLUMN IF NOT EXISTS description_norm text
    GENERATED ALWAYS AS ( lower( translate(coalesce(description,''), 'Ёё', 'Ее') ) ) STORED;

-- FTS index using our custom config
CREATE INDEX IF NOT EXISTS videos_fts_yt_multi_idx ON videos
USING GIN (
  to_tsvector('yt_multi', coalesce(title_norm,'') || ' ' || coalesce(description_norm,''))
);

-- Trigram indexes on normalized columns (accelerate fuzzy)
CREATE INDEX IF NOT EXISTS videos_title_trgm_norm ON videos
USING GIN (title_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS videos_description_trgm_norm ON videos
USING GIN (description_norm gin_trgm_ops);

-- Author username trigram (likely exists already)
CREATE INDEX IF NOT EXISTS users_username_trgm ON users
USING GIN (username gin_trgm_ops);