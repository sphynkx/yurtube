-- PostgreSQL schema for MVP (UTC timestamps).
-- Incorporates: case-insensitive username uniqueness, anonymous views,
-- content flags (age/kids), tags, categories, and video assets for sprites/VTT.
-- Adds: video editing fields, embed defaults, renditions table.
-- IDs are text; length checks where applicable.

BEGIN;

-- Users
CREATE TABLE IF NOT EXISTS users (
    user_uid      TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user', -- 'user' | 'admin' | 'moderator'
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    password_changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_channel_id_len CHECK (char_length(channel_id) = 24),
    CONSTRAINT users_username_fmt CHECK (username ~ '^[A-Za-z0-9_.-]{3,30}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uidx ON users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uidx ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS users_channel_id_uidx ON users (channel_id);
CREATE INDEX IF NOT EXISTS users_password_changed_at_idx ON users(password_changed_at);

CREATE TABLE IF NOT EXISTS sso_identities (
    provider      TEXT NOT NULL,
    subject       TEXT NOT NULL,
    user_uid      TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    email         TEXT,
    display_name  TEXT,
    picture_url   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject)
);

CREATE INDEX IF NOT EXISTS sso_identities_user_idx ON sso_identities(user_uid);
CREATE INDEX IF NOT EXISTS sso_identities_email_idx ON sso_identities(email);

-- User assets (avatar)
CREATE TABLE IF NOT EXISTS user_assets (
    user_uid   TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('avatar')),
    path       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_uid, asset_type)
);

-- Categories (single category per video, optional)
CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Videos
CREATE TABLE IF NOT EXISTS videos (
    video_id             TEXT PRIMARY KEY,
    author_uid           TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    title                TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    duration_sec         INTEGER NOT NULL DEFAULT 0 CHECK (duration_sec >= 0),
    status               TEXT NOT NULL CHECK (status IN ('public','private','unlisted')),
    processing_status    TEXT NOT NULL DEFAULT 'uploaded' CHECK (processing_status IN ('uploaded','processing','ready','failed')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    views_count          INTEGER NOT NULL DEFAULT 0 CHECK (views_count >= 0),
    likes_count          INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
    is_age_restricted    BOOLEAN NOT NULL DEFAULT FALSE,
    is_made_for_kids     BOOLEAN NOT NULL DEFAULT FALSE,
    category_id          TEXT NULL REFERENCES categories(category_id) ON DELETE SET NULL,
    storage_path         TEXT NOT NULL,
    allow_comments       BOOLEAN NOT NULL DEFAULT TRUE,
    allow_embed          BOOLEAN NOT NULL DEFAULT TRUE,
    embed_params         JSONB   NOT NULL DEFAULT '{}'::jsonb,
    license              TEXT    NOT NULL DEFAULT 'standard',
    thumb_pref_offset    INTEGER NOT NULL DEFAULT 0 CHECK (thumb_pref_offset >= 0),
    comments_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    comments_root_doc_id TEXT NULL,
    thumbnails_ready    BOOLEAN NOT NULL DEFAULT FALSE,
    captions_vtt         TEXT NULL,
    captions_lang        VARCHAR(8) NULL,
    captions_meta        JSONB NULL,
    captions_ready       BOOLEAN NOT NULL DEFAULT FALSE,
    captions_alt         JSONB NULL,-- Future translations container

    CONSTRAINT videos_video_id_len CHECK (char_length(video_id) = 12)
);

CREATE INDEX IF NOT EXISTS videos_author_created_idx ON videos (author_uid, created_at DESC);
CREATE INDEX IF NOT EXISTS videos_status_created_idx ON videos (status, created_at DESC);
CREATE INDEX IF NOT EXISTS videos_created_idx ON videos (created_at DESC);
CREATE INDEX IF NOT EXISTS videos_category_idx ON videos (category_id);
CREATE INDEX IF NOT EXISTS idx_videos_comments_enabled ON videos(comments_enabled);
UPDATE videos SET comments_enabled = true WHERE comments_enabled IS NULL;

-- Reactions
CREATE TABLE IF NOT EXISTS reactions (
    reaction_uid  TEXT PRIMARY KEY,
    user_uid      TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    video_id      TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    reaction_type TEXT NOT NULL CHECK (reaction_type IN ('like','dislike')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS reactions_user_video_uidx ON reactions (user_uid, video_id);
CREATE INDEX IF NOT EXISTS reactions_video_type_idx ON reactions (video_id, reaction_type);

-- Views (anonymous supported)
CREATE TABLE IF NOT EXISTS views (
    view_uid      TEXT PRIMARY KEY,
    user_uid      TEXT REFERENCES users(user_uid) ON DELETE SET NULL,
    video_id      TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    watched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_sec  INTEGER NOT NULL DEFAULT 0 CHECK (duration_sec >= 0)
    -- Optional future fields for dedup: viewer_fingerprint TEXT, ip_hash TEXT
);

CREATE INDEX IF NOT EXISTS views_video_time_idx ON views (video_id, watched_at DESC);
CREATE INDEX IF NOT EXISTS views_user_time_idx ON views (user_uid, watched_at DESC);

-- Subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_uid TEXT PRIMARY KEY,
    subscriber_uid   TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    channel_uid      TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT subscriptions_self_subscribe CHECK (subscriber_uid <> channel_uid)
);

CREATE UNIQUE INDEX IF NOT EXISTS subscriptions_pair_uidx ON subscriptions (subscriber_uid, channel_uid);
CREATE INDEX IF NOT EXISTS subscriptions_subscriber_idx ON subscriptions (subscriber_uid);
CREATE INDEX IF NOT EXISTS subscriptions_channel_idx ON subscriptions (channel_uid);

-- Playlists
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id  TEXT PRIMARY KEY,
    owner_uid    TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS playlists_owner_created_idx ON playlists (owner_uid, created_at DESC);

-- Playlists core schema (MVP) with indices and cascade behavior.
-- Uses TEXT ids consistent with existing schema. Visibility/type/order are TEXT with CHECK constraints.

-- (1) Playlists table
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id      TEXT PRIMARY KEY,
    owner_uid        TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    name             TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    description      TEXT,
    visibility       TEXT NOT NULL CHECK (visibility IN ('private','unlisted','public')),
    type             TEXT NOT NULL CHECK (type IN ('user','system_watch_later','system_favorites')),
    parent_id        TEXT REFERENCES playlists(playlist_id) ON DELETE SET NULL,  -- for future hierarchy
    cover_asset_path TEXT,                                                      -- playlist cover image (relative storage path)
    is_loop          BOOLEAN NOT NULL DEFAULT FALSE,                            -- loop playback flag
    ordering_mode    TEXT NOT NULL DEFAULT 'manual' CHECK (ordering_mode IN ('manual','added_at_desc','popularity')),
    share_token      TEXT UNIQUE,                                               -- optional unlisted share token
    items_count      INTEGER NOT NULL DEFAULT 0,                                 -- cached count of items
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Helpful indices for common queries
CREATE INDEX IF NOT EXISTS playlists_owner_idx ON playlists (owner_uid);
CREATE INDEX IF NOT EXISTS playlists_owner_visibility_idx ON playlists (owner_uid, visibility, created_at DESC);
CREATE INDEX IF NOT EXISTS playlists_parent_idx ON playlists (parent_id);

-- Ensure only one system_watch_later per user
CREATE UNIQUE INDEX IF NOT EXISTS playlists_unique_watch_later_per_user_uidx
    ON playlists (owner_uid)
    WHERE type = 'system_watch_later';

-- Ensure only one system_favorites per user
CREATE UNIQUE INDEX IF NOT EXISTS playlists_unique_favorites_per_user_uidx
    ON playlists (owner_uid)
    WHERE type = 'system_favorites';

-- (2) Playlist items table
-- Composite PK enforces unique (playlist_id, video_id) and is efficient for ordered listing.
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id  TEXT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    video_id     TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),  -- manual order
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (playlist_id, video_id)
);

-- Indices optimized for listing and maintenance
CREATE INDEX IF NOT EXISTS playlist_items_order_idx ON playlist_items (playlist_id, position, video_id);
CREATE INDEX IF NOT EXISTS playlist_items_added_idx ON playlist_items (playlist_id, added_at DESC);
CREATE INDEX IF NOT EXISTS playlist_items_video_idx ON playlist_items (video_id);

-- (3) Lightweight triggers to maintain items_count and updated_at
-- Keep schema self-contained; no heavy logic, just counters.

CREATE OR REPLACE FUNCTION playlist_items_count_trigger() RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE playlists
      SET items_count = items_count + 1,
          updated_at = NOW()
      WHERE playlist_id = NEW.playlist_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE playlists
      SET items_count = GREATEST(items_count - 1, 0),
          updated_at = NOW()
      WHERE playlist_id = OLD.playlist_id;
    RETURN OLD;
  ELSE
    RETURN NULL;
  END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS playlist_items_count_ai ON playlist_items;
DROP TRIGGER IF EXISTS playlist_items_count_ad ON playlist_items;

CREATE TRIGGER playlist_items_count_ai
  AFTER INSERT ON playlist_items
  FOR EACH ROW
  EXECUTE PROCEDURE playlist_items_count_trigger();

CREATE TRIGGER playlist_items_count_ad
  AFTER DELETE ON playlist_items
  FOR EACH ROW
  EXECUTE PROCEDURE playlist_items_count_trigger();

-- Tags (many-to-many)
CREATE TABLE IF NOT EXISTS tags (
    tag_id     TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS video_tags (
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    tag_id   TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, tag_id)
);

-- Video assets (spritesheets, VTT, default thumbs, etc.)
CREATE TABLE IF NOT EXISTS video_assets (
    asset_id    TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    asset_type  TEXT NOT NULL, -- 'storyboard_vtt' | 'sprite_sheet' | 'thumbnail_default' | 'thumbnail_anim' | 'subtitle_vtt' | ...
    path        TEXT NOT NULL, -- relative to storage root
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS video_assets_video_type_uidx ON video_assets (video_id, asset_type);

-- Video renditions (per-quality outputs, queued/processed by worker)
CREATE TABLE IF NOT EXISTS video_renditions (
  rendition_id  BIGSERIAL PRIMARY KEY,
  video_id      TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
  preset        TEXT NOT NULL,                      -- e.g. 1080p, 720p, 480p
  codec         TEXT NOT NULL DEFAULT 'vp9',        -- e.g. vp9, av1, h264
  status        TEXT NOT NULL DEFAULT 'queued',     -- queued, processing, ready, error
  storage_path  TEXT,                               -- set when ready
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (video_id, preset, codec)
);

CREATE INDEX IF NOT EXISTS idx_video_renditions_video ON video_renditions(video_id);
CREATE INDEX IF NOT EXISTS idx_video_renditions_status ON video_renditions(status);

-- Notifications subsystem schema
CREATE TABLE IF NOT EXISTS notifications (
    notif_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_uid TEXT NOT NULL,
    type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ NULL,
    agg_key TEXT NULL,
    dedupe_key TEXT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_uid, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_uid) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);

CREATE TABLE IF NOT EXISTS user_notification_prefs (
    user_uid TEXT NOT NULL,
    type TEXT NOT NULL,
    inapp BOOLEAN NOT NULL DEFAULT TRUE,
    email BOOLEAN NOT NULL DEFAULT FALSE,
    allow_unlisted BOOLEAN NULL,
    PRIMARY KEY (user_uid, type)
);

-- Captions translations table (future; minimal columns now)
CREATE TABLE IF NOT EXISTS video_captions (
    video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    lang        VARCHAR(8) NOT NULL,
    rel_path    TEXT NULL,
    status      TEXT NOT NULL DEFAULT 'pending', -- pending|ready|failed
    meta        JSONB NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (video_id, lang)
);
CREATE INDEX IF NOT EXISTS video_captions_video_idx ON video_captions(video_id);

--------------------------------------------------------------------
-- ytconvert jobs (requests + tracking)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ytconvert_jobs (
  job_id              TEXT PRIMARY KEY,
  video_id            TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
  author_uid          TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
  state               TEXT NOT NULL DEFAULT 'REQUESTED',
  requested_variants  JSONB NOT NULL DEFAULT '[]'::jsonb,
  grpc_job_id         TEXT,
  progress_percent    INT NOT NULL DEFAULT 0,
  message             TEXT NOT NULL DEFAULT '',
  meta                JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ytconvert_jobs_video_id ON ytconvert_jobs(video_id);
CREATE INDEX IF NOT EXISTS idx_ytconvert_jobs_state ON ytconvert_jobs(state);
CREATE INDEX IF NOT EXISTS idx_ytconvert_jobs_grpc_job_id ON ytconvert_jobs(grpc_job_id);

COMMIT;