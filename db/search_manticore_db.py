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

# Public API (stable):
# - http_sql_select_raw(sql: str) -> str
# - http_sql_select(sql: str) -> Union[Dict[str, Any], List[Any]]
# - http_sql_raw_post(sql: str) -> Tuple[bool, str]
# - run_cli(sql: str) -> Tuple[bool, str]
#
# Internals are selected by SEARCH_INDEX_TRANSPORT:
#   "manticore_http": direct HTTP to Manticore (default), CLI fallback
#   "service_http": HTTP calls to an external service exposing /select and /exec

class _Transport:
    def http_sql_select_raw(self, sql: str) -> str:
        raise NotImplementedError

    def http_sql_select(self, sql: str) -> Union[Dict[str, Any], List[Any]]:
        raw = self.http_sql_select_raw(sql)
        try:
            return json.loads(raw)
        except Exception:
            return {"error": "invalid json", "raw": raw[:500]}

    def http_sql_raw_post(self, sql: str) -> Tuple[bool, str]:
        raise NotImplementedError

    def run_cli(self, sql: str) -> Tuple[bool, str]:
        # Optional implementation
        return False, "CLI not available in this transport"


class _ManticoreHttpTransport(_Transport):
    def _base_http(self) -> str:
        return f"http://{settings.MANTICORE_HOST}:{settings.MANTICORE_HTTP_PORT}/sql"

    def http_sql_select_raw(self, sql: str) -> str:
        base = self._base_http()
        payload = {"query": sql}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(base, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            # Graceful fallback to GET, and if GET also fails — return an empty JSON to avoid 500 upstream.
            try:
                qs = urllib.parse.urlencode({"query": sql})
                url = f"{base}?{qs}"
                with urllib.request.urlopen(url, timeout=10) as resp2:
                    return resp2.read().decode("utf-8")
            except Exception as e2:
                log.error("Manticore http_sql_select_raw failed: POST err=%r; GET err=%r", e, e2)
                # Return an empty result instead of raising to allow upper layers to fallback.
                return "{}"

    def http_sql_raw_post(self, sql: str) -> Tuple[bool, str]:
        base = self._base_http()
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

    def _cli_available(self) -> str:
        explicit = os.getenv("MANTICORE_CLI_PATH")
        if explicit and os.path.isfile(explicit):
            return explicit
        path = shutil.which("mysql")
        return path or ""

    def run_cli(self, sql: str) -> Tuple[bool, str]:
        mysql_bin = self._cli_available()
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


class _ServiceHttpTransport(_Transport):
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def _post_json(self, path: str, payload: Dict[str, Any], timeout: float = 15.0) -> Tuple[int, str]:
        url = f"{self.base}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8")

    def http_sql_select_raw(self, sql: str) -> str:
        code, body = self._post_json("/select", {"query": sql}, timeout=20.0)
        if code >= 400:
            raise RuntimeError(f"index service select HTTP {code}")
        return body

    def http_sql_raw_post(self, sql: str) -> Tuple[bool, str]:
        try:
            code, body = self._post_json("/exec", {"query": sql}, timeout=25.0)
            if code >= 400:
                return False, f"index service exec HTTP {code}"
            try:
                obj = json.loads(body)
            except Exception:
                obj = {}
            if isinstance(obj, dict) and obj.get("ok") is False:
                return False, str(obj.get("error") or "")
            return True, ""
        except Exception as e:
            return False, repr(e)


def _make_transport() -> _Transport:
    mode = (settings.SEARCH_INDEX_TRANSPORT or "manticore_http").strip().lower()
    if mode == "service_http":
        base = (settings.SEARCH_INDEX_SERVICE_URL or "").strip()
        if not base:
            log.error("SEARCH_INDEX_SERVICE_URL is not set; fallback to manticore_http")
        else:
            return _ServiceHttpTransport(base)
    return _ManticoreHttpTransport()

_TRANSPORT = _make_transport()

def http_sql_select_raw(sql: str) -> str:
    return _TRANSPORT.http_sql_select_raw(sql)

def http_sql_select(sql: str) -> Union[Dict[str, Any], List[Any]]:
    return _TRANSPORT.http_sql_select(sql)

def http_sql_raw_post(sql: str) -> Tuple[bool, str]:
    return _TRANSPORT.http_sql_raw_post(sql)

def run_cli(sql: str) -> Tuple[bool, str]:
    return _TRANSPORT.run_cli(sql)