

## Download repo
```bash
cd /var/www
git clone https://github.com/sphynkx/yurtube
cd yurtube
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

Install ffmpeg (ffprobe comes with the same package)
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

Apply schema creation and seed data (initial categories/tags):
```bash
PGPASSWORD='SECRET' psql -U yt_user -h 127.0.0.1 -d yt_db -f install/schema.sql
PGPASSWORD='SECRET' psql -U yt_user -h 127.0.0.1 -d yt_db -f install/seed.sql
```



## Configure application .env
Copy sample:
```bash
cp install/.env-sample .env
```
 and edit params/secrets:
* DATABASE_URL=postgresql://yt_user:SECRET@127.0.0.1:5432/yt_db
* SECRET_KEY=replace-with-strong-secret
* STORAGE_ROOT=/var/www/yurtube/storage
* SESSION_COOKIE_SECURE=true


## Create admin account
```bash
./run.sh bootstrap-admin
```
Enter username, email, password for admin-user.


## Search engines
Application supports two search engines. You may configure both of them and switch via `.env` parameter. Default is Postgres FTS.


### Postgres FTS
Apply schema:
```bash
PGPASSWORD='SECRET' psql -U yt_user -h 127.0.0.1 -d yt_db -f install/postgres/ddl/videos_fts.sql
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
where "XXXXXXXXXXXX" id ID of edited video. You could get record about modified video.

To force reindex search DB use script `install/manticore/reindex_all.py`:
```bash
source ../../.venv/bin/activate
python3 reindex_all.py
deactivate
```

## Run the app
Create system user for app, ensure storage directory exists and is writable:
```bash
sudo useradd --system --home-dir /var/www/yurtube --shell /usr/sbin/nologin yurtube || true
sudo mkdir -p /var/www/yurtube
sudo chown -R yurtube:yurtube /var/www/yurtube
```
and:
```bash
./run.sh
```

## Nginx
On external hosting server - create `/etc/nginx/conf.d/yurtube.conf`:
```conf
server {
        server_name  yurtube.sphynkx.org.ua;
        listen       80;
        access_log   /var/log/nginx/yurtube-access.log  main;
        error_log   /var/log/nginx/yurtube-error.log;
        location / {
        proxy_pass      http://192.168.7.3:8077;
        proxy_connect_timeout       600;
        proxy_send_timeout          600;
        proxy_read_timeout          600;
        send_timeout                600;
        }
}
```
Then:
```bash
service nginx restart
letsencrypt
```
Choose subdomain and set option __2__. 


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



