-- PostgreSQL schema for MVP (UTC timestamps).
-- Incorporates: case-insensitive username uniqueness, anonymous views,
-- content flags (age/kids), tags, categories, and video assets for sprites/VTT.
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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_channel_id_len CHECK (char_length(channel_id) = 24),
    CONSTRAINT users_username_fmt CHECK (username ~ '^[A-Za-z0-9_.-]{3,30}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uidx ON users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uidx ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS users_channel_id_uidx ON users (channel_id);

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
    video_id           TEXT PRIMARY KEY,
    author_uid         TEXT NOT NULL REFERENCES users(user_uid) ON DELETE CASCADE,
    title              TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    duration_sec       INTEGER NOT NULL DEFAULT 0 CHECK (duration_sec >= 0),
    status             TEXT NOT NULL CHECK (status IN ('public','private','unlisted')),
    processing_status  TEXT NOT NULL DEFAULT 'uploaded' CHECK (processing_status IN ('uploaded','processing','ready','failed')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    views_count        INTEGER NOT NULL DEFAULT 0 CHECK (views_count >= 0),
    likes_count        INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
    is_age_restricted  BOOLEAN NOT NULL DEFAULT FALSE,
    is_made_for_kids   BOOLEAN NOT NULL DEFAULT FALSE,
    category_id        TEXT NULL REFERENCES categories(category_id) ON DELETE SET NULL,
    storage_path       TEXT NOT NULL,
    CONSTRAINT videos_video_id_len CHECK (char_length(video_id) = 12)
);

CREATE INDEX IF NOT EXISTS videos_author_created_idx ON videos (author_uid, created_at DESC);
CREATE INDEX IF NOT EXISTS videos_status_created_idx ON videos (status, created_at DESC);
CREATE INDEX IF NOT EXISTS videos_created_idx ON videos (created_at DESC);
CREATE INDEX IF NOT EXISTS videos_category_idx ON videos (category_id);

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

-- Playlist items
CREATE TABLE IF NOT EXISTS playlist_items (
    item_uid     TEXT PRIMARY KEY,
    playlist_id  TEXT NOT NULL REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    video_id     TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS playlist_items_unique_vid_per_playlist_uidx ON playlist_items (playlist_id, video_id);
CREATE INDEX IF NOT EXISTS playlist_items_playlist_position_idx ON playlist_items (playlist_id, position);

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
    asset_type  TEXT NOT NULL, -- 'storyboard_vtt' | 'sprite_sheet' | 'thumbnail_default' | 'subtitle_vtt' | ...
    path        TEXT NOT NULL, -- relative to storage root
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS video_assets_video_type_uidx ON video_assets (video_id, asset_type);

COMMIT;