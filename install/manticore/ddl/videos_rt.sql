-- Manticore RT index (table) for videos
CREATE TABLE IF NOT EXISTS videos_rt (
  id            BIGINT,
  video_id      STRING,
  title         TEXT,
  description   TEXT,
  tags          TEXT,
  author        TEXT,
  category      STRING,
  status        STRING,
  created_at    TIMESTAMP,
  views         INT,
  likes         INT,
  lang          STRING
)
morphology='stem_enru'
min_infix_len='2'
index_exact_words='1'
html_strip='1'
charset_table='non_cjk, U+0400..U+04FF -> U+0400..U+04FF'
stopwords='';