#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-8080}"

APP_ENV="${APP_ENV:-development}"
AUTO_CREATE_TABLES="${AUTO_CREATE_TABLES:-false}"
SECRET_KEY="${SECRET_KEY:-dev-secret-do-not-use-in-production}"
DATABASE_URL="${DATABASE_URL:-sqlite:///${ROOT_DIR}/game.db}"

API_PID=""
WEB_PID=""

cleanup() {
  set +e
  if [[ -n "${WEB_PID}" ]] && kill -0 "${WEB_PID}" 2>/dev/null; then
    kill "${WEB_PID}" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

ensure_python_deps() {
  if "${PYTHON_BIN}" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    return 0
  fi
  echo "[dev_up] Installing Python dependencies (editable)..."
  "${PYTHON_BIN}" -m pip install -e '.[dev]'
}

ensure_node_deps() {
  if [[ -d "${ROOT_DIR}/web/node_modules" ]]; then
    return 0
  fi
  echo "[dev_up] Installing web dependencies..."
  (cd web && npm install)
}

wait_for_api() {
  echo "[dev_up] Waiting for API health..."
  "${PYTHON_BIN}" - <<PY
import json
import sys
import time
import urllib.error
import urllib.request

url = "http://${API_HOST}:${API_PORT}/api/health"
deadline = time.time() + 30
last_err = None

while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            body = r.read().decode("utf-8", "replace")
        data = json.loads(body)
        if data.get("status") == "ok":
            print("[dev_up] API is up:", url)
            sys.exit(0)
        last_err = f"unexpected response: {data!r}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        last_err = repr(e)
    time.sleep(0.5)

print("[dev_up] API did not become healthy in time:", url)
print("[dev_up] last error:", last_err)
sys.exit(1)
PY
}

ensure_python_deps
ensure_node_deps

echo "[dev_up] Migrating database (alembic)..."
APP_ENV="${APP_ENV}" SECRET_KEY="${SECRET_KEY}" DATABASE_URL="${DATABASE_URL}" \
  "${PYTHON_BIN}" - <<'PY'
import os
import sqlite3
import subprocess
import sys

from sqlalchemy.engine.url import make_url

DB_URL = os.environ.get("DATABASE_URL", "")

def run_alembic(*args: str) -> int:
    cmd = [sys.executable, "-m", "alembic", "-c", "server/alembic.ini", *args]
    return subprocess.call(cmd)

url = make_url(DB_URL)
if url.drivername.startswith("sqlite"):
    path = url.database
    if not path:
        raise SystemExit(run_alembic("upgrade", "head"))

    con = sqlite3.connect(path)
    cur = con.cursor()

    def has_table(name: str) -> bool:
        cur.execute("select 1 from sqlite_master where type='table' and name=?", (name,))
        return cur.fetchone() is not None

    def runs_has_column(col: str) -> bool:
        if not has_table("runs"):
            return False
        cur.execute("pragma table_info(runs)")
        cols = {row[1] for row in cur.fetchall()}
        return col in cols

    has_alembic = has_table("alembic_version")
    alembic_has_row = False
    if has_alembic:
        try:
            cur.execute("select version_num from alembic_version limit 1")
            row = cur.fetchone()
            alembic_has_row = bool(row and row[0])
        except sqlite3.Error:
            alembic_has_row = False
    has_schema = has_table("guests") or has_table("users") or has_table("runs")

    # If schema was created via create_all() previously, there is no alembic_version
    # table and "upgrade head" will fail trying to create existing tables. We stamp to
    # a baseline revision and then upgrade forward if needed.
    if has_schema and (not has_alembic or not alembic_has_row):
        if runs_has_column("personality_reveal_ack"):
            print("[dev_up] Existing schema detected; stamping alembic to head.")
            raise SystemExit(run_alembic("stamp", "head"))
        else:
            print("[dev_up] Existing schema detected; stamping alembic to 20260213_0002 then upgrading head.")
            rc = run_alembic("stamp", "20260213_0002")
            if rc != 0:
                raise SystemExit(rc)
            raise SystemExit(run_alembic("upgrade", "head"))

    raise SystemExit(run_alembic("upgrade", "head"))

raise SystemExit(run_alembic("upgrade", "head"))
PY

echo "[dev_up] Starting API on http://${API_HOST}:${API_PORT} ..."
APP_ENV="${APP_ENV}" AUTO_CREATE_TABLES="${AUTO_CREATE_TABLES}" SECRET_KEY="${SECRET_KEY}" DATABASE_URL="${DATABASE_URL}" \
  "${PYTHON_BIN}" -m uvicorn server.app.main:app --reload --host "${API_HOST}" --port "${API_PORT}" &
API_PID="$!"

wait_for_api

echo "[dev_up] Starting web on http://${WEB_HOST}:${WEB_PORT} ..."
(cd web && npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}") &
WEB_PID="$!"

echo ""
echo "[dev_up] Web: http://${WEB_HOST}:${WEB_PORT}"
echo "[dev_up] API: http://${API_HOST}:${API_PORT}/api/health"
echo "[dev_up] Press Ctrl+C to stop."
echo ""

while true; do
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "[dev_up] API process exited."
    exit 1
  fi
  if ! kill -0 "${WEB_PID}" 2>/dev/null; then
    echo "[dev_up] Web process exited."
    exit 1
  fi
  sleep 1
done
