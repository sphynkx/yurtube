-- Manticore RT index (table) for subtitle segments (future)
CREATE TABLE IF NOT EXISTS subtitles_rt (
  id            BIGINT,
  video_id      STRING,
  start_sec     INT,
  lang          STRING,
  content       TEXT
)
morphology='stem_enru'
min_infix_len='2'
index_exact_words='0'
html_strip='1'
charset_table='non_cjk, U+0400..U+04FF -> U+0400..U+04FF'
stopwords='';