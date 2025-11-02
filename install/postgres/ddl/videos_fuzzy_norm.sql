SET search_path TO public;

ALTER TABLE videos
  ADD COLUMN IF NOT EXISTS title_fuzzy text
    GENERATED ALWAYS AS (
      lower(
        replace(
          replace(
            translate(coalesce(title,''), 'ЁёЭэ', 'ЕеЕе'),
          'эй','ей'),
        'йо','ио')
      )
    ) STORED,
  ADD COLUMN IF NOT EXISTS description_fuzzy text
    GENERATED ALWAYS AS (
      lower(
        replace(
          replace(
            translate(coalesce(description,''), 'ЁёЭэ', 'ЕеЕе'),
          'эй','ей'),
        'йо','ио')
      )
    ) STORED;

CREATE INDEX IF NOT EXISTS videos_title_fuzzy_trgm ON videos USING GIN (title_fuzzy gin_trgm_ops);
CREATE INDEX IF NOT EXISTS videos_description_fuzzy_trgm ON videos USING GIN (description_fuzzy gin_trgm_ops);