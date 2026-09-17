#!/usr/bin/env bash
set -euo pipefail

# Test scripts directory (this directory, e.g. deye-cloud/test/)
TEST_DIR="$(cd "$(dirname "$0")" && pwd)"

# Lock file lives at deye-cloud/deye_refresh.lock. Resolve the deye-cloud script
# dir relative to this test script (the parent of TEST_DIR) so the suite works
# no matter which cwd it is invoked from. An explicit SCRIPT_DIR env var still
# takes precedence.
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$TEST_DIR/.." && pwd)}"
SCRIPT_DIR="$(cd "$SCRIPT_DIR" && pwd)"
LOCK_FILE="$SCRIPT_DIR/deye_refresh.lock"
DB_FILE="$SCRIPT_DIR/deye_solar_data.db"

TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() { echo "✅ PASS: $1"; TESTS_PASSED=$((TESTS_PASSED + 1)); }
fail() { echo "❌ FAIL: $1"; TESTS_FAILED=$((TESTS_FAILED + 1)); }

# Provide dummy credentials via the environment so the module-level credential
# check passes. load_dotenv() does NOT override existing env vars, so these win
# over any real .env — and we never create or delete a real .env file (the lock
# tests do not hit the API, so real credentials are never needed).
export DEYE_APP_ID="test_app_id"
export DEYE_APP_SECRET="test_app_secret"
export DEYE_EMAIL="test@example.com"
export DEYE_PASSWORD="abc123"
export DEYE_INVERTER_SN="TEST123"

echo "=============================================="
echo "Lock File Guard — Test Suite"
echo "=============================================="

# ── Test 1: Lock file does not exist, script acquires it ──
echo ""
echo "--- Test 1: Lock acquisition on fresh start ---"
rm -f "$LOCK_FILE"

cat > "$TEST_DIR/test_lock_acquire.py" << PYEOF
import sys, os, json
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("FAIL: Could not acquire lock")
    sys.exit(1)

lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deye_refresh.lock')
if os.path.exists(lock_path):
    with open(lock_path) as f:
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

if DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_acquire.py" 2>&1; then
    pass "Lock file created with correct JSON format"
else
    fail "Lock file creation failed"
fi

# ── Test 2: Concurrent execution is rejected ──
echo ""
echo "--- Test 2: Concurrent execution rejection ---"
rm -f "$LOCK_FILE"

cat > "$TEST_DIR/test_lock_hold.py" << PYEOF
import sys, os, signal, time
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    sys.exit(1)

# Hold lock for 10 seconds
time.sleep(10)
_release_lock()
PYEOF

cat > "$TEST_DIR/test_lock_concurrent.py" << PYEOF
import sys, os, signal
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
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
DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_hold.py" &
HOLDER_PID=$!
sleep 1

# Try to acquire in foreground
if DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_concurrent.py" 2>&1; then
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

cat > "$TEST_DIR/test_lock_stale.py" << PYEOF
import sys, os, signal
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
signal.signal(signal.SIGTERM, _lock_cleanup)
signal.signal(signal.SIGINT, _lock_cleanup)
if not _acquire_lock():
    print("FAIL: Should have cleared stale lock")
    sys.exit(1)
else:
    print("Correctly cleared stale lock and acquired new one")
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deye_refresh.lock')
    if os.path.exists(lock_path):
        print("Lock file exists after acquiring")
        _release_lock()
        sys.exit(0)
    else:
        print("FAIL: Lock file not found after acquire")
        sys.exit(1)
PYEOF

if DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_stale.py" 2>&1; then
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

cat > "$TEST_DIR/test_lock_force.py" << PYEOF
import sys, os
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
_force_lock()
print("Force lock cleared successfully")
sys.exit(0)
PYEOF

if DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_force.py" 2>&1; then
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

cat > "$TEST_DIR/test_lock_signal.py" << PYEOF
import sys, os, signal
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
signal.signal(signal.SIGTERM, _lock_cleanup)
if not _acquire_lock():
    sys.exit(1)

# Wait for signal
print(f"PID {os.getpid()} waiting for SIGTERM...")
import subprocess
subprocess.call(["kill", "-TERM", str(os.getpid())])
# This line should not be reached
print("FAIL: Should have exited")
sys.exit(1)
PYEOF

DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_signal.py" &
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

cat > "$TEST_DIR/test_lock_corrupt.py" << PYEOF
import sys, os, signal
sys.path.insert(0, '.')
exec(open(os.path.join(os.path.dirname(__file__), '..', 'deye-logger.py')).read().split('if __name__')[0])

os.chdir(os.path.dirname(__file__))
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

if DEYE_SCRIPT_DIR="$SCRIPT_DIR" python3 "$TEST_DIR/test_lock_corrupt.py" 2>&1; then
    pass "Corrupt lock file correctly handled"
else
    fail "Corrupt lock file handling failed"
fi

# ── Summary ──
echo ""
echo "=============================================="
echo "Test Results: $TESTS_PASSED passed, $TESTS_FAILED failed"
echo "=============================================="

# Cleanup
rm -f "$LOCK_FILE" "$TEST_DIR/test_lock_*.py"

if [ $TESTS_FAILED -gt 0 ]; then
    exit 1
fi
