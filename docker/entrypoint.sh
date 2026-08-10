#!/bin/sh
set -eu

DB_PATH="${WORLDOS_DB:-/data/world.db}"
HOST="${WORLDOS_HOST:-0.0.0.0}"
PORT="${WORLDOS_PORT:-8765}"

ensure_parent() {
  mkdir -p "$(dirname "$DB_PATH")"
}

case "${1:-inspector}" in
  inspector)
    ensure_parent
    if [ ! -f "$DB_PATH" ] && [ "${WORLDOS_AUTO_INIT:-false}" = "true" ]; then
      worldos-living init --db "$DB_PATH"
    fi
    exec worldos-inspector --db "$DB_PATH" --host "$HOST" --port "$PORT"
    ;;
  mcp)
    ensure_parent
    exec worldos-mcp
    ;;
  init)
    ensure_parent
    if [ -f "$DB_PATH" ]; then
      echo "Database already exists at $DB_PATH; refusing to reinitialize." >&2
      exit 2
    fi
    exec worldos-living init --db "$DB_PATH"
    ;;
  run)
    ensure_parent
    if [ ! -f "$DB_PATH" ]; then
      echo "WorldOS database not found at $DB_PATH" >&2
      exit 1
    fi
    shift
    exec worldos-living run --db "$DB_PATH" "$@"
    ;;
  backup)
    ensure_parent
    if [ ! -f "$DB_PATH" ]; then
      echo "WorldOS database not found at $DB_PATH" >&2
      exit 1
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    destination="${WORLDOS_BACKUP_DIR:-/backups}/world-${stamp}.db"
    mkdir -p "$(dirname "$destination")"
    python - "$DB_PATH" "$destination" <<'PY'
import sqlite3
import sys

source, destination = sys.argv[1:3]
with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)
with sqlite3.connect(destination) as check:
    result = check.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"backup integrity check failed: {result}")
print(destination)
PY
    ;;
  shell)
    shift
    exec /bin/sh "$@"
    ;;
  *)
    exec "$@"
    ;;
esac