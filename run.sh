#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run.sh [command]

Commands:
  deps             Create venv (if missing) and install dependencies
  bootstrap-admin  Run one-time admin bootstrap inside venv
  serve            Start the app with uvicorn (default)

Environment:
  Reads .env automatically if present
EOF
}

load_env() {
  if [ -f ".env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source ".env"
    set +o allexport
  fi
}

ensure_venv() {
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

cmd="${1:-serve}"

load_env

case "${cmd}" in
  deps)
    ensure_venv
    pip install --upgrade pip
    pip install -r install/requirements.txt
    ;;

  bootstrap-admin)
    ensure_venv
    pip install --upgrade pip
    pip install -r install/requirements.txt
    python install/bootstrap_admin.py
    ;;

  serve)
    ensure_venv
##    pip install --upgrade pip
##    pip install -r install/requirements.txt
    : "${APP_HOST:=0.0.0.0}"
    : "${APP_PORT:=8077}"
    exec uvicorn main:app --host "${APP_HOST}" --port "${APP_PORT}" --workers 4 --http httptools --loop uvloop --proxy-headers --forwarded-allow-ips="192.168.7.1"
    ;;

  -h|--help|help)
    usage
    ;;

  *)
    echo "Unknown command: ${cmd}" >&2
    usage
    exit 1
    ;;
esac