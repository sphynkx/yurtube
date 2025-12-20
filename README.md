[YurTube](https://yurtube.sphynkx.org.ua/) is a self‑hosted video hosting engine written in Python and built on FastAPI, PostgreSQL, MongoDB, Redis+Celery, Manticore, ffmpeg etc. UX is inspired by [Youtube service](https://www.youtube.com/) and [ClipBucket engine](https://github.com/sphynkx/clipbucket-v5), with a modular design that runs cleanly on a single host or scales out by moving services to external nodes via configuration.

Highlights
* Accounts and authentication: local sign‑in and SSO (Google, X)
* Two video players: a custom YouTube‑style player and a simple HTML5 player
* Uploading and editing videos with automatic thumbnails, animated previews
* Sprites generation
* Generation and display captions
* Watch and embed videos
* Search by two search engines
* Comments with like/dislike and persistent user votes
* Channels and subscriptions, user avatars, responsive UI


Application is WIP now. Available base functional:
* Register and authentification - local and SSO (Gmail, X)
* Two video players - custom (fully inspired by Youtube's one) and simple standard.
* View and embed videos
* Upload and edit videos:
  * generation of animated previews
  * Sprites generation (by [separate microservice](https://github.com/sphynkx/ytsprites))
  * Captions generation (by [separate microservice](https://github.com/sphynkx/ytcms))
* Two Search engines ([Manticore](https://manticoresearch.com/) and Postgres FTS)
* Comments by [separate microservice](https://github.com/sphynkx/ytcomments)
* Notifications system
* Unified extendable storage system (by [separate microservice](https://github.com/sphynkx/ytstorage))

Design notes
* Modular by default: swap or externalize services through config without code changes
* Scales from a single instance to multi‑server deployments as your load grows


# Base install and config
For a minimal version with limited functionality, installing this app is sufficient. However, for full functionality, there are separate services with separate repositories:

* [ytcms](https://github.com/sphynkx/ytcms) - service for captions generation
* [ytcomments](https://github.com/sphynkx/ytcomments) - service for comments
* [ytsprites](https://github.com/sphynkx/ytsprites) - service for WebVTT sprites generation
* [ytstorage](https://github.com/sphynkx/ytstorage) - service for external storage systems

These could be installed and configured separately. About this see below in the appropriate sections.

__Note__: This installation is designed for the Fedora distribution, but with appropriate modifications, it can be used on other distributions as well. However, some issues have been noted, such as the fact that FFMpeg is supplied in a stripped-down form in Debian-based distributions and requires a special build. This issue primarily affects external services and can be resolved through dockerization.


## Download and install app
```bash
cd /var/www
git clone https://github.com/sphynkx/yurtube
cd yurtube
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r install/requirements.txt
deactivate
chmod a+x run.sh
```


## Install ffmpeg
```bash
sudo dnf install -y ffmpeg
```

If not found, enable RPM Fusion (free + nonfree), then install:
```bash
sudo dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm  -E %fedora).noarch.rpm https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
```

Optionaly - swap ffmpeg-free to full ffmpeg if your system has ffmpeg-free preinstalled
```bash
sudo dnf -y swap ffmpeg-free ffmpeg --allowerasing
```

Install `ffmpeg` (`ffprobe` comes with the same package)
```bash
sudo dnf install -y ffmpeg
```

Verify:
```bash
which ffmpeg && ffmpeg -version
which ffprobe && ffprobe -version
```


## Create and configure DB (Postgres)

Find and configure `pg_hba.conf`. Add entries for the app database and user (defaults):

```bash
# YurTube app
local   yt_db           yt_user                   scram-sha-256
host    yt_db           yt_user   127.0.0.1/32   scram-sha-256
host    yt_db           yt_user   ::1/128        scram-sha-256
```

Reload PostgreSQL config:
```bash
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

Create role and database. Replace SECRET with `yt_user`'s password:
```bash
sudo -u postgres psql -v db_pass='SECRET' -f install/prep.sql
```
Set user password for DB user (replace "SECRET" with actual password):
```bash
export PGPASSWORD='SECRET'
```

Apply schema creation and seed data (initial categories/tags):
```bash
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/schema.sql
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/seed.sql
```


## Configure DB for comments engine (MongoDB)
__Note__: This section will be deprecated for app, due to implementation of new external [ytcomments](https://github.com/sphynkx/ytcomments) - see below. Local functional still works as legacy but may switched off.

At the `.env` fill fields:
```conf
# MongoDB
MONGO_HOST=127.0.0.1
MONGO_PORT=27017
MONGO_DB_NAME=yt_comments
MONGO_USER=yt_user
MONGO_PASSWORD=SECRET
```
according your configuration.

Edit `/etc/mongod.conf` - temporarily disable `security` section, restart mongodb:
```bash
systemctl restart mongod
```
Copy sample file with mono user configuring:
```bash
cp install/mongo_setup.js-sample install/mongo_setup.js
```
Edit it - set password and apply:
```bash
mongosh < install/mongo_setup.js
```
Edit `/etc/mongod.conf` again - enable `security` section, restart mongodb:
```bash
service mongod restart
```
Dont forget to remove `install/mongo_setup.js`.


### MongoDB tuning
Optional recommendations in case then service periodically falls down. 

Modify `/etc/mongod.conf`, set `storage` section so:
```conf
storage:
  dbPath: /var/lib/mongo
  journal:
    enabled: true
#  engine:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 1.5
```
Find unit file `mongod.service` (mostly in `/usr/lib/systemd/system/`). In the `[Service]` section add:
```conf
Restart=on-failure
RestartSec=10s
StartLimitBurst=5
StartLimitIntervalSec=60s
OOMScoreAdjust=-900
MemoryAccounting=true
```
Then copy it to `/etc/systemd/system` and update systemd configuration:
```bash
cp /usr/lib/systemd/system/mongod.service /etc/systemd/system
systemctl daemon-reload
systemctl restart mongod
systemctl status mongod.service
```


## Notifications (Redis + Celery)
```bash
dnf install redis && systemctl enable --now redis
cp install/yurtube-celery-notifications.service /etc/systemd/system
cp install/yurtube-celery-notifications-beat.service /etc/systemd/system

sudo systemctl daemon-reload
sudo systemctl enable --now yurtube-celery-notifications.service yurtube-celery-notifications-beat.service
```
Check:
```bash
redis-cli ping
```
Expect: `PONG`

Also see `config/notifications_cfg.py` - it consists default params for localhost. You may redefine them in `.env`.


## Configure application .env
Copy sample:
```bash
cp install/.env-sample .env
```
 and edit params/secrets:
```conf
DATABASE_URL=postgresql://yt_user:SECRET@127.0.0.1:5432/yt_db
SECRET_KEY=replace-with-strong-secret
APP_STORAGE_FS_ROOT=/var/www/yurtube/storage
SESSION_COOKIE_SECURE=true
```


## Create admin account
```bash
./run.sh bootstrap-admin
```
Enter username, email, password for admin-user.


## SSO configuration
Go to [Google Cloud Console](https://console.cloud.google.com/), create new Web-app, config it, get secrets, set them to `.env` also.

Go to [Twitter Dev Portal](https://developer.x.com/en/portal/petition/essential/basic-info), create new Web-app, config it, get secrets, set them to `.env` also.


## Search engines
Application supports two search engines. You may configure both of them and switch via `.env` parameter. Default is Postgres FTS.

At first:
```bash
sudo dnf install hunspell-ru hunspell-en postgresql-contrib postgresql-devel
install/dicts_prep.sh
```


### Postgres FTS
Apply schemas:
```bash
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/postgres/ddl/videos_fts.sql
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/postgres/ddl/fts_config.sql
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/postgres/ddl/videos_norm_fts.sql
psql -U yt_user -h 127.0.0.1 -d yt_db -f install/postgres/ddl/videos_fuzzy_norm.sql
```
or via single script:
```bash
install/postgres/apply_db_schema.sh
```

In the `.env` set `SEARCH_BACKEND` to "postgres". Restart app.


### Manticore Search
For Fedora distribution:
```bash
sudo rpm --import https://repo.manticoresearch.com/GPG-KEY-manticore
sudo dnf install https://repo.manticoresearch.com/manticore-repo.noarch.rpm
```
Edit `/etc/yum.repos.d/manticore.repo` - replace "$releasever" to "9". Install packages:
```bash
sudo dnf install manticore
```

Switch app to Manticore engine: in the `.env` set `SEARCH_BACKEND` to "manticore".

Create tables and check them:
```bash
mysql -h 127.0.0.1 -P 9306 -e "SOURCE install/manticore/ddl/videos_rt.sql"
mysql -h 127.0.0.1 -P 9306 -e "SOURCE install/manticore/ddl/subtitles_rt.sql"
mysql -h 127.0.0.1 -P 9306 -e "SHOW TABLES"
curl -s 'http://127.0.0.1:9308/sql?mode=raw&query=SHOW%20TABLES'
```
Next check. Edit some video - do some modification in Meta section (for example Description) and save. Next run 
```bash
mysql -h 127.0.0.1 -P 9306 -e "SELECT video_id,title,status FROM videos_rt WHERE video_id='XXXXXXXXXXXX'"
```
where "XXXXXXXXXXXX" is ID of edited video. You could get record about modified video.

To force reindex search DB use script `install/manticore/reindex_all.py`:
```bash
source ../../.venv/bin/activate
python3 reindex_all.py
deactivate
```


### Caption generation service (external)
This is separate service based on gRPC+protobuf and faster-whisper. It installs as separate service on the same or external server. See [its repo](https://github.com/sphynkx/ytcms) for details about it's install and configuration.

At app config you need to set IP address (`YTCMS_HOST`) and port (`YTCMS_PORT`) of `ytcms` service, `YTCMS_TOKEN` same as on service side. Also make sure that file `services/ytcms/ytcms_proto/captions.proto` is identical with one at `ytcms` service. If not - you have to regenerate stubs:
```bash
cd services/ytcms_proto
./gen_proto.sh
```


### Comments service (external)
This is separate microservice for work with client side comments service. It communicates with MongoDB and exchanges info with app's client side part. To install and configure - see [ytcomments repo](https://github.com/sphynkx/ytcomments).

To configure app to work with service set options in the `.env`:
```conf
#YTCOMMENTS_ENABLED=false ## switch to legacy mech
YTCOMMENTS_ENABLED=true
YTCOMMENTS_TRANSPORT=grpc
YTCOMMENTS_ADDR=127.0.0.1:9093
YTCOMMENTS_TRANSPORT=grpc
YTCOMMENTS_TLS_ENABLED=false
YTCOMMENTS_TIMEOUT_MS=3000
YTCOMMENTS_FORCE_SERVICE_READ=1
```
In case of MongoDB falling issues you may apply some tunings for it - see [ytcomments repo](https://github.com/sphynkx/ytcomments)) for details.

Make sure that the `services/ytcomments/ytcomments.proto` is same as one for the `ytcomments`. Otherwise run `gen_proto.sh` to regenerate protobuf files.


### Sprites preview service (external)
This is separate service for generation sprites preview, based on gRPC+protobuf. It could be installed locally or on some other server. Download it from [this repository](https://github.com/sphynkx/ytsprites), follow [instructions](https://github.com/sphynkx/ytsprites/README.md) for install, configure and run. 

Configure app to communicate with that service - set necessary params to `.env`, about params and current defaults - see in the `config/ytsprites/ytsprites_cfg.py`.

Also make sure that file `services/ytsprites/ytsprites_proto/ytsprites.proto` is identical with one at `ytsprites` service. If not - you have to regenerate stubs:
```bash
cd services/ytsprites/ytsprites_proto
./gen_proto.sh
```


### Storage system (external)
This step is optional - by default app uses local `storage/` dir.

App supports storage layer abstraction and allow to use local directory and/or remote service as storage. See details in [ytstorage repository](https://github.com/sphynkx/ytstorage).

After install need to configure ytstorage params:
- `STORAGE_PROVIDER` - switch to remote service: set it from "local" to "remote" 
- `STORAGE_REMOTE_ADDRESS` - remote host and port
- `STORAGE_REMOTE_TLS` - set true to use auth
- `STORAGE_REMOTE_TOKEN` - set token same as on service side

Check `services/storage/storage_proto/ytstorage.proto`. It must be same as one in `ytstorage` installation. Otherwise you need regenerate proto files.. Just run `gen_proto.sh` in the same dir.


## Run the app manually
Create system user for app, ensure storage directory exists and is writable:
```bash
sudo useradd --system --home-dir /var/www/yurtube --shell /usr/sbin/nologin yurtube || true
sudo chown -R yurtube:yurtube /var/www/yurtube
```
and:
```bash
./run.sh
```


## Configure as a systemd service (Fedora)
Copy systemd unit file:
```bash
cp install/yurtube.service /etc/systemd/system/yurtube.service
```
Make dir for logs:
```bash
mkdir -p /var/log/uvicorn
```
Reload and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yurtube.service
sudo systemctl status yurtube.service
journalctl -u yurtube.service -f
```
Firewall (if needed):
```bash
sudo firewall-cmd --add-port=8077/tcp --permanent
sudo firewall-cmd --reload
```


## Nginx
This is case of external hosting server that proxying to another server with app. On external hosting server - create `/etc/nginx/conf.d/yurtube.conf`:
```conf
# upstream to VM
upstream vm_app {
    server 192.168.7.3:8077;
    keepalive 32;
}

# May be duplicated with nginx.conf. First check `nginx -t`
proxy_buffering on;
proxy_buffers 64 16k;
proxy_busy_buffers_size 256k;
proxy_read_timeout 120s;
#sendfile on;
#tcp_nopush on;
#tcp_nodelay on;
#keepalive_timeout 65s;
open_file_cache max=1000 inactive=60s;
open_file_cache_valid 120s;
open_file_cache_min_uses 2;

# Dont forget create appropriate dirs:
# Previews cache
proxy_cache_path /var/cache/nginx/thumbs levels=1:2 keys_zone=thumbs:50m max_size=1g inactive=30d use_temp_path=off;

# Videos cache (slice, 206)
proxy_cache_path /var/cache/nginx/video levels=1:2 keys_zone=video:200m max_size=20g inactive=7d use_temp_path=off;

# Microchache for dynamicals
proxy_cache_path /var/cache/nginx/micro levels=1:2 keys_zone=micro:20m max_size=1g inactive=30s use_temp_path=off;

map $http_range $nocache_no_range {
    default 0;
    ""      1;
}


server {
    server_name  yurtube.sphynkx.org.ua;

    access_log   /var/log/nginx/yurtube-access.log  main;
    error_log    /var/log/nginx/yurtube-error.log;

    # Microcache for init state of player
    location /videos/react/state {
        # Cache key by `video_id`
        set $state_key "";
        if ($args ~* "video_id=([^&]+)") {
            set $state_key "state:$1";
        }

        proxy_cache micro;
        proxy_cache_key $state_key;
        proxy_cache_valid 200 5s;
        proxy_cache_lock on;
        add_header X-Microcache $upstream_cache_status always;

        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host   $host;
        proxy_set_header X-Forwarded-Proto  https;

        proxy_pass http://vm_app;
    }

    # Slice-cache for video (Range/206)
    # 1. Cache full 200
    # 2. Force snt to client 206 from cache
    # 3. Cache key w/o $slice_range !! Full 200
    location ~* ^/internal/storage/file/.+\.(webm|mp4|mkv|mov)$ {
        proxy_cache_key $uri;
        proxy_cache video;
        proxy_cache_methods GET HEAD;

        # Full cache
        proxy_cache_valid 200 7d;
        # Optional 206 caching for upstream
        proxy_cache_valid 206 7d;

        # Force send 206 to client from cached 200
        proxy_force_ranges on;

        proxy_cache_lock on;
        proxy_cache_background_update on;

        # Allow caching ignoring Set-Cookie
        proxy_ignore_headers Set-Cookie Expires;
        # Dont send them to client
        proxy_hide_header Set-Cookie;

        add_header X-Cache $upstream_cache_status always;
        add_header X-Video-Location "matched" always;

        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host   $host;
        proxy_set_header X-Forwarded-Proto  https;

        proxy_pass http://vm_app;
    }

    # Long cache for animated previews and other imgs
    location ~* ^/internal/storage/file/.+\.(jpg|jpeg|png|webp|gif)$ {
        proxy_cache thumbs;
        proxy_cache_valid 200 30d;
        proxy_cache_lock on;
        proxy_ignore_headers Expires Set-Cookie;
        add_header Cache-Control "public, max-age=2592000, immutable" always;
        add_header X-Cache $upstream_cache_status always;

        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host   $host;
        proxy_set_header X-Forwarded-Proto  https;

        proxy_pass http://vm_app;
    }

    location / {
        proxy_http_version 1.1;

        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host   $host;
        proxy_set_header X-Forwarded-Proto  https;

        proxy_pass http://vm_app;
    }
}
```

Then:
```bash
mkdir -p /var/cache/nginx/{micro,thumbs,video}
service nginx restart
letsencrypt
```
Choose subdomain and set option __2__. 

