#!/usr/bin/env python3
"""
Mock of deye-cloud/deye-logger.py for frontend background-refresh tests (#89).

The real ingestion script needs a Deye Cloud .env file, which is absent in the
dev/test environment. This mock implements the same interface that the backend
`POST /api/refresh` endpoint relies on:

  - no arguments
  - exit code 0 on success (non-zero on failure)
  - progress/success lines on stdout, errors on stderr

It simulates a slow Deye Cloud sync (default 3 s, override with
MOCK_REFRESH_SLEEP) so the "refreshing ..." status-bar indicator is observable
in the UI while the refresh is in flight.

Start the server with the mock:

  DEYE_LOGGER_SCRIPT="$(pwd)/frontend/test/mock_deye_logger.py" bash backend/start.sh
"""

import os
import sys
import time

sleep_seconds = float(os.environ.get("MOCK_REFRESH_SLEEP", "3"))

print(f"[mock deye-logger] simulating Deye Cloud sync ({sleep_seconds}s)...")
sys.stdout.flush()
time.sleep(sleep_seconds)
print("[mock deye-logger] Mock refresh completed successfully (no database changes).")
sys.exit(0)
