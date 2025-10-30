-- Idempotent DB bootstrap for YurTube (psql-only, no DO blocks).
-- Defaults (can be overridden via -v):
--   db_user = yt_user
--   db_name = yt_db
--   db_pass = SECRET

\if :{?db_user}
\else
\set db_user yt_user
\endif

\if :{?db_name}
\else
\set db_name yt_db
\endif

\if :{?db_pass}
\else
\set db_pass SECRET
\endif

\echo Using db_user=:db_user db_name=:db_name

-- Ensure role
SELECT 1 AS role_exists FROM pg_roles WHERE rolname = :'db_user' \gset
\if :{?role_exists}
  \echo Role :db_user exists -> ALTER PASSWORD
  ALTER ROLE :db_user WITH LOGIN PASSWORD :'db_pass';
\else
  \echo Creating role :db_user
  CREATE ROLE :db_user LOGIN PASSWORD :'db_pass';
\endif

-- Ensure database
SELECT 1 AS db_exists FROM pg_database WHERE datname = :'db_name' \gset
\if :{?db_exists}
  \echo Database :db_name already exists
\else
  \echo Creating database :db_name owned by :db_user
  CREATE DATABASE :db_name OWNER :db_user TEMPLATE template0 ENCODING 'UTF8';
\endif

-- Grants (owner already has all privileges; keep for clarity)
GRANT ALL PRIVILEGES ON DATABASE :db_name TO :db_user;