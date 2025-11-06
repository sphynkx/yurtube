import json
import logging
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple, Union

from services.search.settings_srch import settings

log = logging.getLogger(__name__)


def http_sql_select_raw(sql: str) -> str:
    """
    Execute raw SQL over Manticore HTTP endpoint. Returns raw text.
    """
    base = f"http://{settings.MANTICORE_HOST}:{settings.MANTICORE_HTTP_PORT}/sql"
    payload = {"query": sql}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        qs = urllib.parse.urlencode({"query": sql})
        url = f"{base}?{qs}"
        with urllib.request.urlopen(url, timeout=10) as resp2:
            return resp2.read().decode("utf-8")


def http_sql_select(sql: str) -> Union[Dict[str, Any], List[Any]]:
    """
    Execute SQL over HTTP and parse JSON if possible. Otherwise return an error object.
    """
    raw = http_sql_select_raw(sql)
    try:
        return json.loads(raw)
    except Exception:
        return {"error": "invalid json", "raw": raw[:500]}


def _cli_available() -> str:
    explicit = os.getenv("MANTICORE_CLI_PATH")
    if explicit and os.path.isfile(explicit):
        return explicit
    path = shutil.which("mysql")
    return path or ""


def run_cli(sql: str) -> Tuple[bool, str]:
    """
    Execute SQL via mysql CLI against Manticore (fallback path).
    """
    mysql_bin = _cli_available()
    if not mysql_bin:
        return False, "mysql CLI not found (set MANTICORE_CLI_PATH or install mysql client)"
    cmd = [mysql_bin, "-h", settings.MANTICORE_HOST, "-P", "9306", "-N", "-B", "-e", sql]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        if res.returncode != 0:
            return False, res.stderr.strip()
        return True, ""
    except Exception as e:
        return False, repr(e)


def http_sql_raw_post(sql: str) -> Tuple[bool, str]:
    """
    POST raw SQL to Manticore HTTP endpoint (mode=raw). Returns (ok, message).
    """
    base = f"http://{settings.MANTICORE_HOST}:{settings.MANTICORE_HTTP_PORT}/sql"
    form = urllib.parse.urlencode({"mode": "raw", "query": sql}).encode("utf-8")
    req = urllib.request.Request(base, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                obj = json.loads(body)
                if isinstance(obj, dict) and obj.get("error"):
                    err = str(obj.get("error"))
                    log.error("Manticore raw-post error: %s", err)
                    return False, err
            except Exception:
                pass
            return True, ""
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = f"HTTP {e.code}: {err_body.strip()}"
        log.error("Manticore HTTPError during raw-post: %s", msg)
        return False, msg
    except Exception as e:
        log.exception("Manticore raw-post failed: %s", e)
        return False, repr(e)