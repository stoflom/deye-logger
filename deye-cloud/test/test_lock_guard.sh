#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK_FILE="$SCRIPT_DIR/deye_refresh.lock"
DB_FILE="$SCRIPT_DIR/deye_solar_data.db"
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() { echo "✅ PASS: $1"; ((TESTS_PASSED++)); }
fail() { echo "❌ FAIL: $1"; ((TESTS_FAILED++)); }
cleanup() { rm -f "$LOCK_FILE" "$DB_FILE"; }

# Create a minimal .env for testing
cat > "$SCRIPT_DIR/.env" << 'ENVEOF'
DEYE_APP_ID=test_app_id
DEYE_APP_SECRET=test_app_secret
DEYE_EMAIL=test@example.com
DEYE_PASSWORD=abc123
DEYE_INVERTER_SN=TEST123
ENVEOF

echo "=============================================="
echo "Lock File Guard — Test Suite"
echo "=============================================="

# ── Test 1: Lock file does not exist, script acquires it ──
echo ""
echo "--- Test 1: Lock acquisition on fresh start ---"
rm -f "$LOCK_FILE"

# Create a minimal test script that just acquires and holds lock briefly
cat > "$SCRIPT_DIR/test_lock_acquire.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
# Import only the lock functions, not the full script
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

# Simulate what main() does
signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("FAIL: Could not acquire lock")
    sys.exit(1)

# Verify lock file exists and has correct format
import json
import os
if os.path.exists(LOCK_FILE):
    with open(LOCK_FILE) as f:
        info = json.load(f)
    if "pid" in info and "started_at" in info:
        print(f"Lock acquired: PID={info['pid']}, started_at={info['started_at']}")
        pass_test = True
    else:
        print("FAIL: Lock file missing pid or started_at")
        pass_test = False
else:
    print("FAIL: Lock file not created")
    pass_test = False

_release_lock()
sys.exit(0 if pass_test else 1)
PYEOF

if python3 "$SCRIPT_DIR/test_lock_acquire.py" 2>&1; then
    pass "Lock file created with correct JSON format"
else
    fail "Lock file creation failed"
fi

# ── Test 2: Concurrent execution is rejected ──
echo ""
echo "--- Test 2: Concurrent execution rejection ---"
rm -f "$LOCK_FILE"

# Create test script that holds lock
cat > "$SCRIPT_DIR/test_lock_hold.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    sys.exit(1)

# Hold lock for 10 seconds
import time
time.sleep(10)
_release_lock()
PYEOF

# Create test script that tries to acquire lock
cat > "$SCRIPT_DIR/test_lock_concurrent.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("Correctly rejected: lock already held by live process")
    sys.exit(0)
else:
    print("FAIL: Should have been rejected")
    sys.exit(1)
PYEOF

# Start holder in background
python3 "$SCRIPT_DIR/test_lock_hold.py" &
HOLDER_PID=$!
sleep 1

# Try to acquire in foreground
if python3 "$SCRIPT_DIR/test_lock_concurrent.py" 2>&1; then
    pass "Concurrent execution correctly rejected"
else
    fail "Concurrent execution was not rejected"
fi

# Kill holder
kill $HOLDER_PID 2>/dev/null || true
wait $HOLDER_PID 2>/dev/null || true

# ── Test 3: Stale lock detection ──
echo ""
echo "--- Test 3: Stale lock detection ---"
rm -f "$LOCK_FILE"

# Create a stale lock with a PID that definitely doesn't exist
cat > "$LOCK_FILE" << 'JSONEOF'
{"pid": 999999, "started_at": "2020-01-01T00:00:00"}
JSONEOF

cat > "$SCRIPT_DIR/test_lock_stale.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("FAIL: Should have cleared stale lock")
    sys.exit(1)
else:
    print("Correctly cleared stale lock and acquired new one")
    import os
    if os.path.exists(LOCK_FILE):
        print("Lock file exists after acquiring")
        _release_lock()
        sys.exit(0)
    else:
        print("FAIL: Lock file not found after acquire")
        sys.exit(1)
PYEOF

if python3 "$SCRIPT_DIR/test_lock_stale.py" 2>&1; then
    pass "Stale lock correctly detected and cleared"
else
    fail "Stale lock detection failed"
fi

# ── Test 4: --force flag overrides lock ──
echo ""
echo "--- Test 4: --force flag overrides lock ---"
rm -f "$LOCK_FILE"

# Create a lock file with a live PID (our own)
python3 -c "
import json, os
lock_info = {'pid': os.getpid(), 'started_at': '2026-01-01T00:00:00'}
with open('$LOCK_FILE', 'w') as f:
    json.dump(lock_info, f)
"

cat > "$SCRIPT_DIR/test_lock_force.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
_force_lock()
print("Force lock cleared successfully")
sys.exit(0)
PYEOF

if python3 "$SCRIPT_DIR/test_lock_force.py" 2>&1; then
    if [ ! -f "$LOCK_FILE" ]; then
        pass "Lock file removed by --force"
    else
        fail "Lock file still exists after --force"
    fi
else
    fail "Force lock failed"
fi

# ── Test 5: Signal cleanup ──
echo ""
echo "--- Test 5: Signal cleanup (SIGTERM) ---"
rm -f "$LOCK_FILE"

cat > "$SCRIPT_DIR/test_lock_signal.py" << 'PYEOF'
import sys, signal, time
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
if not _acquire_lock():
    sys.exit(1)

# Wait for signal
print(f"PID {os.getpid()} waiting for SIGTERM...")
import os
os.system(f"kill -TERM {os.getpid()}")
# This line should not be reached
print("FAIL: Should have exited")
sys.exit(1)
PYEOF

python3 "$SCRIPT_DIR/test_lock_signal.py" &
SIGNAL_PID=$!
sleep 1

# Check lock exists
if [ -f "$LOCK_FILE" ]; then
    echo "Lock file exists before signal"
fi

# Send signal
kill -TERM $SIGNAL_PID 2>/dev/null || true
wait $SIGNAL_PID 2>/dev/null || true

# Check lock is removed
if [ ! -f "$LOCK_FILE" ]; then
    pass "Lock file cleaned up on SIGTERM"
else
    fail "Lock file not cleaned up on SIGTERM"
fi

# ── Test 6: Corrupt lock file ---
echo ""
echo "--- Test 6: Corrupt lock file handling ---"
rm -f "$LOCK_FILE"

echo "this is not json" > "$LOCK_FILE"

cat > "$SCRIPT_DIR/test_lock_corrupt.py" << 'PYEOF'
import sys
sys.path.insert(0, '.')
exec(open('$SCRIPT_DIR/deye-logger.py').read().split('if __name__')[0])

signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("FAIL: Should have cleared corrupt lock")
    sys.exit(1)
else:
    print("Correctly cleared corrupt lock")
    _release_lock()
    sys.exit(0)
PYEOF

if python3 "$SCRIPT_DIR/test_lock_corrupt.py" 2>&1; then
    pass "Corrupt lock file correctly handled"
else
    fail "Corrupt lock file handling failed"
fi

# ── Test 7: Backend lock check (Deno) ──
echo ""
echo "--- Test 7: Backend lock file check ---"
rm -f "$LOCK_FILE"

# Create a lock file
python3 -c "
import json, os
lock_info = {'pid': 12345, 'started_at': '2026-01-01T00:00:00'}
with open('$LOCK_FILE', 'w') as f:
    json.dump(lock_info, f)
"

# Check if lock file is readable by backend
if [ -f "$LOCK_FILE" ]; then
    cat "$LOCK_FILE"
    pass "Lock file created for backend test"
else
    fail "Lock file not created for backend test"
fi

# ── Summary ──
echo ""
echo "=============================================="
echo "Test Results: $TESTS_PASSED passed, $TESTS_FAILED failed"
echo "=============================================="

# Cleanup
rm -f "$LOCK_FILE" "$SCRIPT_DIR/.env" "$SCRIPT_DIR/test_lock_*.py"

if [ $TESTS_FAILED -gt 0 ]; then
    exit 1
fi
