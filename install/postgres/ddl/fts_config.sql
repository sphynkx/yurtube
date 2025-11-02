SET search_path TO public;

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_ts_dict d JOIN pg_namespace n ON n.oid=d.dictnamespace
    WHERE d.dictname='unaccent_dict'
  ) THEN
    CREATE TEXT SEARCH DICTIONARY unaccent_dict (
      TEMPLATE = unaccent,
      RULES    = 'unaccent'
    );
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_ts_dict d JOIN pg_namespace n ON n.oid=d.dictnamespace
    WHERE d.dictname='ru_ispell'
  ) THEN
    BEGIN
      CREATE TEXT SEARCH DICTIONARY ru_ispell (
        TEMPLATE = ispell,
        DictFile = 'ru_utf8',
        AffFile  = 'ru_utf8'
      );
    EXCEPTION WHEN others THEN
      NULL;
    END;
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_ts_dict d JOIN pg_namespace n ON n.oid=d.dictnamespace
    WHERE d.dictname='en_ispell'
  ) THEN
    BEGIN
      CREATE TEXT SEARCH DICTIONARY en_ispell (
        TEMPLATE = ispell,
        DictFile = 'en_utf8',
        AffFile  = 'en_utf8'
      );
    EXCEPTION WHEN others THEN
      NULL;
    END;
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_ts_config c JOIN pg_namespace n ON n.oid=c.cfgnamespace
    WHERE c.cfgname='yt_multi'
  ) THEN
    CREATE TEXT SEARCH CONFIGURATION yt_multi (COPY = simple);
  END IF;
END$$;

DO $$
DECLARE have_ru boolean; have_en boolean;
BEGIN
  SELECT EXISTS (SELECT 1 FROM pg_ts_dict d JOIN pg_namespace n ON n.oid=d.dictnamespace WHERE d.dictname='ru_ispell') INTO have_ru;
  SELECT EXISTS (SELECT 1 FROM pg_ts_dict d JOIN pg_namespace n ON n.oid=d.dictnamespace WHERE d.dictname='en_ispell') INTO have_en;

  IF have_ru AND have_en THEN
    EXECUTE $SQL$
      ALTER TEXT SEARCH CONFIGURATION yt_multi
      ALTER MAPPING FOR word, hword, hword_part
      WITH unaccent_dict, ru_ispell, russian_stem, en_ispell, english_stem, simple
    $SQL$;
  ELSIF have_ru THEN
    EXECUTE $SQL$
      ALTER TEXT SEARCH CONFIGURATION yt_multi
      ALTER MAPPING FOR word, hword, hword_part
      WITH unaccent_dict, ru_ispell, russian_stem, simple
    $SQL$;
  ELSE
    EXECUTE $SQL$
      ALTER TEXT SEARCH CONFIGURATION yt_multi
      ALTER MAPPING FOR word, hword, hword_part
      WITH unaccent_dict, russian_stem, simple
    $SQL$;
  END IF;
END$$;