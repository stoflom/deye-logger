#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Defaults ──────────────────────────────────────────────────────
HOST=""
PORT=""
DB_PATH=""

# ── Parse arguments ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "Usage: bash start.sh [-h] [-H <host>] [-p <port>] [-d <db_path>]"
      echo ""
      echo "Options:"
      echo "  -h, --help          Show this help message"
      echo "  -H, --host <host>   Host to bind to (default: localhost)"
      echo "  -p, --port <port>   Port to listen on (default: 8090)"
      echo "  -d, --db <path>     Path to the SQLite database"
      exit 0
      ;;
    -H|--host)
      if [[ $# -lt 2 ]]; then
        echo "Error: -H/--host requires a value." >&2
        exit 1
      fi
      HOST="$2"
      shift 2
      ;;
    -p|--port)
      if [[ $# -lt 2 ]]; then
        echo "Error: -p/--port requires a value." >&2
        exit 1
      fi
      PORT="$2"
      shift 2
      ;;
    -d|--db)
      if [[ $# -lt 2 ]]; then
        echo "Error: -d/--db requires a value." >&2
        exit 1
      fi
      DB_PATH="$2"
      shift 2
      ;;
    -*)
      echo "Error: Unknown option '$1'. Use -h for help." >&2
      exit 1
      ;;
    *)
      echo "Error: Unexpected argument '$1'. Use -h for help." >&2
      exit 1
      ;;
  esac
done

# ── Build deno command ────────────────────────────────────────────
CMD=("deno" "run" "-A" "main.ts")

if [[ -n "$HOST" ]]; then
  CMD+=("--host" "$HOST")
fi

if [[ -n "$PORT" ]]; then
  CMD+=("--port" "$PORT")
fi

if [[ -n "$DB_PATH" ]]; then
  CMD+=("--db" "$DB_PATH")
fi

# ── Resolve DB path from project root if not provided ─────────────
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
if [[ -z "$DB_PATH" ]]; then
  CMD+=("--db" "$PROJECT_ROOT/deye_solar_data.db")
fi

# ── Always build frontend ─────────────────────────────────────────
echo "Building..."
cd "$SCRIPT_DIR/../frontend"
npx esbuild src/app.ts --bundle --outfile=public/app.js --format=esm --target=es2020
cd "$SCRIPT_DIR"

# ── Kill any existing instance ────────────────────────────────────
LISTEN_PORT="${PORT:-8090}"
lsof -ti:$LISTEN_PORT 2>/dev/null | xargs -r kill || true

# ── Start ─────────────────────────────────────────────────────────
echo "Starting..."
echo "  Command: ${CMD[*]}"
"${CMD[@]}"
