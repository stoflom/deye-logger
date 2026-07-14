#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Build if needed (or source is newer)
if [ ! -f public/app.js ] || [ src/app.ts -nt public/app.js ]; then
  echo "Building..."
  npx esbuild src/app.ts --bundle --outfile=public/app.js --format=esm --target=es2020
fi

# Kill any existing instance on port 8090
lsof -ti:8090 2>/dev/null | xargs -r kill

echo "Starting..."
exec deno run -A main.ts
