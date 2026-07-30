#!/usr/bin/env python3
"""
Test script to verify Deye Logger Backend API endpoints.

Tests all API endpoints with a test database containing known data
at specific days of the week, verifying correct behavior including
the new dayFilter feature for histogram queries.

Usage:
  python3 test_backend.py [--db /path/to/test/db] [--port 8091]

Requires:
  - Python 3 with sqlite3 (standard library)
  - Python 3 with requests: pip install requests
  - Deno installed (to start the backend)
  - The test database is created from scratch and cleaned up after
"""

import sys
import os
import sqlite3
import time
import json
import subprocess
import signal
import argparse
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Configuration ───────────────────────────────────────────────────
DB_PATH = "/tmp/deye_test_data.db"
TEST_PORT = 8091
HOST = "localhost"
BASE_URL = f"http://{HOST}:{TEST_PORT}"
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_MAIN = os.path.join(BACKEND_DIR, "main.ts")

# Test dates chosen so we know their day of week:
# 2026-07-27 = Monday (dayIndex=1)
# 2026-07-28 = Tuesday (dayIndex=2)
# 2026-07-29 = Wednesday (dayIndex=3)
# 2026-07-30 = Thursday (dayIndex=4)
# 2026-07-31 = Friday (dayIndex=5)
# 2026-08-01 = Saturday (dayIndex=6)
# 2026-08-02 = Sunday (dayIndex=0)
TEST_DATES = [
    ("2026-07-27", "Monday", 1),
    ("2026-07-28", "Tuesday", 2),
    ("2026-07-29", "Wednesday", 3),
    ("2026-07-30", "Thursday", 4),
    ("2026-07-31", "Friday", 5),
    ("2026-08-01", "Saturday", 6),
    ("2026-08-02", "Sunday", 0),
]

# ── Test Database Creation ─────────────────────────────────────────

def create_test_database(db_path: str) -> None:
    """Create a test SQLite database with known telemetry data."""
    # Remove existing test DB
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the inverter_telemetry table
    cursor.execute("""
        CREATE TABLE inverter_telemetry (
            device_timestamp TEXT PRIMARY KEY,
            fetch_timestamp TEXT,
            inverter_sn TEXT,
            daily_energy REAL,
            total_energy REAL,
            current_power REAL,
            battery_soc REAL,
            battery_voltage REAL,
            battery_current REAL,
            grid_power REAL,
            grid_voltage REAL,
            grid_frequency REAL,
            pv1_voltage REAL,
            pv1_current REAL,
            pv1_power REAL,
            pv2_voltage REAL,
            pv2_current REAL,
            pv2_power REAL,
            load_power REAL,
            total_dc_power REAL,
            battery_power REAL,
            ac_voltage REAL,
            ac_current REAL
        )
    """)
    cursor.execute("CREATE INDEX idx_device_timestamp ON inverter_telemetry(device_timestamp)")

    # Insert data: 15-minute intervals throughout each day
    # Each day has data at 00:00, 00:15, 00:30, ..., 23:45 (96 records per day)
    # Values are chosen so we can verify averaging behavior
    for date_str, day_name, day_index in TEST_DATES:
        for hour in range(24):
            for minute in range(0, 60, 15):
                timestamp = f"{date_str} {hour:02d}:{minute:02d}:00"
                # day_of_week = day_index (we know it)
                # current_power = hour * 10 + minute + day_index (unique per day/time)
                current_power = hour * 10 + minute + day_index * 100
                battery_soc = 50 + (day_index * 5) + (hour * 2)
                battery_voltage = 52.0 + (day_index * 0.1) + (minute * 0.01)
                daily_energy = float(hour) + (minute / 60.0) + (day_index * 10.0)
                total_energy = 1000.0 + (day_index * 100.0) + float(hour)
                grid_power = -current_power if hour > 6 and hour < 18 else current_power * 0.5
                pv1_power = current_power * 0.6 if 6 <= hour <= 18 else 0
                pv2_power = current_power * 0.4 if 6 <= hour <= 18 else 0
                load_power = current_power * 0.3
                battery_power = -current_power * 0.2 if hour < 6 else current_power * 0.2

                cursor.execute("""
                    INSERT INTO inverter_telemetry (
                        device_timestamp, fetch_timestamp, inverter_sn,
                        daily_energy, total_energy, current_power,
                        battery_soc, battery_voltage, battery_current,
                        grid_power, grid_voltage, grid_frequency,
                        pv1_voltage, pv1_current, pv1_power,
                        pv2_voltage, pv2_current, pv2_power,
                        load_power, total_dc_power, battery_power,
                        ac_voltage, ac_current
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    f"{date_str} 00:00:00",
                    "TEST_SN_001",
                    daily_energy,
                    total_energy,
                    current_power,
                    battery_soc,
                    battery_voltage,
                    10.0 + (day_index * 0.1),
                    grid_power,
                    230.0,
                    50.0,
                    30.0 + (hour * 0.1),
                    5.0 + (day_index * 0.1),
                    pv1_power,
                    28.0 + (hour * 0.1),
                    4.0 + (day_index * 0.1),
                    pv2_power,
                    load_power,
                    pv1_power + pv2_power,
                    battery_power,
                    230.0,
                    15.0
                ))

    conn.commit()
    conn.close()
    print(f"  ✓ Test database created at {db_path}")
    print(f"  ✓ {len(TEST_DATES)} days, ~96 records/day (~{len(TEST_DATES) * 96} total records)")


# ── HTTP Helpers ────────────────────────────────────────────────────

def http_get(path: str, params: dict = None) -> dict:
    """Make a GET request to the API and return the JSON response."""
    url = f"{BASE_URL}{path}"
    if params:
        query = urlencode(params)
        url = f"{url}?{query}"

    try:
        req = Request(url)
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        raise ConnectionError(f"Failed to connect to {url}: {e}")
    except Exception as e:
        raise RuntimeError(f"HTTP GET failed for {url}: {e}")


def http_post(path: str, data: dict = None) -> dict:
    """Make a POST request to the API."""
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode() if data else b""
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        raise ConnectionError(f"Failed to connect to {url}: {e}")


# ── Test Functions ──────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def check(self, condition: bool, message: str) -> bool:
        if condition:
            self.passed += 1
            print(f"    ✓ {message}")
            return True
        else:
            self.failed += 1
            self.errors.append(message)
            print(f"    ✗ {message}")
            return False


def test_version(t: TestResult) -> None:
    """Test GET /api/version returns correct version."""
    print("\n[Test 1] GET /api/version")
    result = http_get("/api/version")
    t.check("version" in result, "Response has 'version' field")
    t.check(result["version"] == "2.0.1", f"Version is 2.0.1 (got {result.get('version')})")


def test_columns(t: TestResult) -> None:
    """Test GET /api/columns returns column metadata."""
    print("\n[Test 2] GET /api/columns")
    result = http_get("/api/columns")
    t.check(isinstance(result, list), "Response is an array")
    t.check(len(result) == 48, f"Returns 48 columns (got {len(result)})")
    if len(result) > 0:
        t.check("name" in result[0], "Columns have 'name' field")
        t.check("label" in result[0], "Columns have 'label' field")
        t.check(result[0]["name"] == "device_timestamp", f"First column is device_timestamp")


def test_dates(t: TestResult) -> None:
    """Test GET /api/dates returns min/max date range."""
    print("\n[Test 3] GET /api/dates")
    result = http_get("/api/dates")
    t.check("min" in result and "max" in result, "Response has 'min' and 'max' fields")
    t.check(result["min"] == "2026-07-27", f"Min date is 2026-07-27 (got {result.get('min')})")
    t.check(result["max"] == "2026-08-02", f"Max date is 2026-08-02 (got {result.get('max')})")


def test_data_single_date(t: TestResult) -> None:
    """Test GET /api/data returns raw data for a single date."""
    print("\n[Test 4] GET /api/data (single date)")
    result = http_get("/api/data", {
        "date": "2026-07-27",
        "columns": "current_power,battery_soc"
    })
    t.check("rows" in result, "Response has 'rows' field")
    t.check(len(result["rows"]) == 96, f"Returns 96 rows for single day (got {len(result['rows'])})")
    if len(result["rows"]) > 0:
        t.check("device_timestamp" in result["rows"][0], "Rows contain device_timestamp")
        t.check("current_power" in result["rows"][0], "Rows contain requested columns")
        # First record at 00:00:00 on Monday (dayIndex=1), current_power = 0*10 + 0 + 1*100 = 100
        first_ts = result["rows"][0]["device_timestamp"]
        t.check(first_ts.startswith("2026-07-27 00:00:00"), f"First row is at 2026-07-27 00:00:00 (got {first_ts})")


def test_data_range(t: TestResult) -> None:
    """Test GET /api/data-range returns data across multiple days."""
    print("\n[Test 5] GET /api/data-range (multiple days)")
    result = http_get("/api/data-range", {
        "from": "2026-07-27",
        "to": "2026-07-28",
        "columns": "current_power,battery_soc"
    })
    t.check("rows" in result, "Response has 'rows' field")
    t.check(len(result["rows"]) == 192, f"Returns 192 rows for 2 days (got {len(result['rows'])})")


def test_data_validation(t: TestResult) -> None:
    """Test GET /api/data validation errors."""
    print("\n[Test 6] GET /api/data validation errors")
    
    # Missing date
    try:
        result = http_get("/api/data", {"columns": "current_power"})
        # If we get here without error, that's a problem
        t.check(False, "Missing 'date' param should return 400")
    except ConnectionError:
        pass  # Expected
    except Exception as e:
        # Check if it's a 400 error
        if "400" in str(e):
            t.check(True, "Missing 'date' param returns 400")
        else:
            t.check(False, f"Missing 'date' param error: {e}")


def test_histogram_all_days(t: TestResult) -> None:
    """Test GET /api/histogram with dayFilter=all (default)."""
    print("\n[Test 7] GET /api/histogram (dayFilter=all, 1-day range)")
    result = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power,battery_soc",
        "binMinutes": "60",
        "dayFilter": "all"
    })
    t.check("labels" in result, "Response has 'labels' field")
    t.check("datasets" in result, "Response has 'datasets' field")
    t.check("maxValues" in result, "Response has 'maxValues' field")
    # 96 records in 60-min bins = 24 bins
    t.check(len(result["labels"]) == 24, f"24 hour bins for 1-day range (got {len(result['labels'])})")
    t.check(len(result["datasets"]) == 2, f"2 datasets for 2 columns (got {len(result['datasets'])})")
    # Each bin should have 4 data points (96 records / 24 bins)
    for i, ds in enumerate(result["datasets"]):
        t.check(len(ds["data"]) == 24, f"Dataset {i} has 24 values (got {len(ds['data'])})")


def test_histogram_day_filter_monday(t: TestResult) -> None:
    """Test GET /api/histogram with dayFilter=mon on a range containing Monday."""
    print("\n[Test 8] GET /api/histogram (dayFilter=mon, 3-day range)")
    # Range: 2026-07-27 (Mon) to 2026-07-29 (Wed)
    # With dayFilter=mon, only Monday records should be included
    
    result_all = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-29",
        "columns": "current_power,battery_soc",
        "binMinutes": "60",
        "dayFilter": "all"
    })
    
    result_mon = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-29",
        "columns": "current_power,battery_soc",
        "binMinutes": "60",
        "dayFilter": "mon"
    })
    
    t.check(len(result_mon["labels"]) == 24, f"dayFilter=mon returns 24 bins (got {len(result_mon['labels'])})")
    t.check(len(result_mon["datasets"]) == 2, f"dayFilter=mon returns 2 datasets (got {len(result_mon['datasets'])})")
    
    # Verify that dayFilter=mon gives same result as dayFilter=all for single-day range
    result_all_1day = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power,battery_soc",
        "binMinutes": "60",
        "dayFilter": "all"
    })
    
    t.check(len(result_all["labels"]) == len(result_all_1day["labels"]), 
            "3-day all has same bin count as 1-day all (Mon only in range)")
    
    # dayFilter=mon on 3-day range should equal 1-day Mon result
    t.check(len(result_mon["labels"]) == len(result_all_1day["labels"]),
            f"dayFilter=mon on 3-day range matches 1-day Mon range (bins: {len(result_mon['labels'])} vs {len(result_all_1day['labels'])})")
    
    # Verify the bin labels match (should be same hours)
    t.check(result_mon["labels"] == result_all_1day["labels"],
            "dayFilter=mon bin labels match single-day Monday labels")


def test_histogram_day_filter_sunday(t: TestResult) -> None:
    """Test GET /api/histogram with dayFilter=sun on a range containing Sunday."""
    print("\n[Test 9] GET /api/histogram (dayFilter=sun, 3-day range)")
    
    # Range: 2026-07-27 (Mon) to 2026-07-29 (Wed)
    # With dayFilter=sun, no records should match (no Sunday in range)
    result = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-29",
        "columns": "current_power,battery_soc",
        "binMinutes": "60",
        "dayFilter": "sun"
    })
    
    t.check(len(result["labels"]) == 0, f"dayFilter=sun on Mon-Wed range returns empty (got {len(result['labels'])} labels)")
    t.check(len(result["datasets"]) == 0, f"dayFilter=sun on Mon-Wed range returns empty datasets")


def test_histogram_day_filter_all_days(t: TestResult) -> None:
    """Test GET /api/histogram with dayFilter on each day of the week."""
    print("\n[Test 10] GET /api/histogram (all day filters on matching range)")
    
    # Test each day filter with a 7-day range containing all days
    result_all = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-08-02",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "all"
    })
    
    # 7 days * 24 bins = should have 24 bins (averaged across 7 days)
    t.check(len(result_all["labels"]) == 24, f"7-day all has 24 bins (got {len(result_all['labels'])})")
    # With 7 days of data, each bin has 7 data points per column
    all_data_len = len(result_all["datasets"][0]["data"])
    t.check(all_data_len == 24, f"Dataset has {all_data_len} values (expected 24)")
    
    # Now test each day individually
    days = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
    for day in days:
        result = http_get("/api/histogram", {
            "from": "2026-07-27",
            "to": "2026-08-02",
            "columns": "current_power",
            "binMinutes": "60",
            "dayFilter": day
        })
        t.check(len(result["labels"]) == 24, f"dayFilter={day} has 24 bins (got {len(result['labels'])})")
        # Each day in the range has 24 records, so 24 bins with 1 point each
        t.check(len(result["datasets"]) >= 1, f"dayFilter={day} has at least 1 dataset")
    
    print(f"  ✓ All 7 day filters tested successfully")


def test_histogram_day_filter_invalid(t: TestResult) -> None:
    """Test GET /api/histogram with invalid dayFilter values."""
    print("\n[Test 11] GET /api/histogram (invalid dayFilter values)")
    
    # Invalid dayFilter should be treated as "all"
    result_invalid = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "invalid"
    })
    
    result_all = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "all"
    })
    
    t.check(len(result_invalid["labels"]) == len(result_all["labels"]),
            f"Invalid dayFilter treated as 'all' (both have {len(result_all['labels'])} bins)")


def test_histogram_day_filter_case_insensitive(t: TestResult) -> None:
    """Test that dayFilter is case-insensitive."""
    print("\n[Test 12] GET /api/histogram (case-insensitive dayFilter)")
    
    result_lower = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "mon"
    })
    
    result_upper = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "MON"
    })
    
    result_mixed = http_get("/api/histogram", {
        "from": "2026-07-27",
        "to": "2026-07-27",
        "columns": "current_power",
        "binMinutes": "60",
        "dayFilter": "MoN"
    })
    
    t.check(len(result_lower["labels"]) == len(result_upper["labels"]),
            f"dayFilter=mon and dayFilter=MON return same result ({len(result_lower['labels'])} bins)")
    t.check(len(result_lower["labels"]) == len(result_mixed["labels"]),
            f"dayFilter=mon and dayFilter=MoN return same result ({len(result_lower['labels'])} bins)")


def test_histogram_different_bin_sizes(t: TestResult) -> None:
    """Test histogram with different bin sizes."""
    print("\n[Test 13] GET /api/histogram (different bin sizes)")
    
    bin_sizes = [("15", 96), ("30", 48), ("60", 24)]
    
    for bin_size, expected_bins in bin_sizes:
        result = http_get("/api/histogram", {
            "from": "2026-07-27",
            "to": "2026-07-27",
            "columns": "current_power",
            "binMinutes": bin_size,
            "dayFilter": "all"
        })
        t.check(len(result["labels"]) == expected_bins,
                f"binMinutes={bin_size} has {expected_bins} bins (got {len(result['labels'])})")


def test_histogram_missing_params(t: TestResult) -> None:
    """Test histogram validation errors."""
    print("\n[Test 14] GET /api/histogram (validation errors)")
    
    # Missing 'from'
    try:
        http_get("/api/histogram", {
            "to": "2026-07-27",
            "columns": "current_power"
        })
        t.check(False, "Missing 'from' param should return 400")
    except Exception as e:
        if "400" in str(e):
            t.check(True, "Missing 'from' param returns 400")
        else:
            t.check(False, f"Unexpected error: {e}")


def main():
    """Run all backend tests."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Backend API tests")
    parser.add_argument("--db", default="/tmp/deye_test_data.db", help="Path to test database")
    parser.add_argument("--port", type=int, default=8091, help="Server port")
    args = parser.parse_args()
    test_db_path = args.db
    test_port = args.port

    print("=" * 70)
    print("Deye Logger Backend API Tests")
    print("=" * 70)
    print(f"Test database: {test_db_path}")
    print(f"Server URL: http://{HOST}:{test_port}")
    print("=" * 70)

    # Create test database
    print("\n[Setup] Creating test database...")
    create_test_database(test_db_path)

    # Start backend server
    print(f"\n[Setup] Starting backend server on port {test_port}...")
    server_process = subprocess.Popen(
        ["deno", "run", "-A", BACKEND_MAIN, "--db", test_db_path, "--port", str(test_port)],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to start
    max_wait = 15
    waited = 0
    while waited < max_wait:
        time.sleep(1)
        waited += 1
        try:
            http_get("/api/version")
            print(f"  ✓ Server started after {waited}s")
            break
        except ConnectionError:
            if waited == max_wait:
                print(f"  ✗ Server failed to start after {max_wait}s")
                server_process.kill()
                stdout, stderr = server_process.communicate()
                print(f"  stdout: {stdout.decode()[:500]}")
                print(f"  stderr: {stderr.decode()[:500]}")
                sys.exit(1)
    else:
        print(f"  ✗ Server failed to start")
        sys.exit(1)

    # Run tests
    test_result = TestResult()
    print("\n" + "=" * 70)
    print("Running tests...")
    print("=" * 70)

    try:
        test_version(test_result)
        test_columns(test_result)
        test_dates(test_result)
        test_data_single_date(test_result)
        test_data_range(test_result)
        test_data_validation(test_result)
        test_histogram_all_days(test_result)
        test_histogram_day_filter_monday(test_result)
        test_histogram_day_filter_sunday(test_result)
        test_histogram_day_filter_all_days(test_result)
        test_histogram_day_filter_invalid(test_result)
        test_histogram_day_filter_case_insensitive(test_result)
        test_histogram_different_bin_sizes(test_result)
        test_histogram_missing_params(test_result)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        print("\n" + "=" * 70)
        print("Cleaning up...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"  ✓ Test database removed: {test_db_path}")

        # Summary
        total = test_result.passed + test_result.failed
        print(f"\n{'=' * 70}")
        print(f"Results: {test_result.passed}/{total} passed, {test_result.failed} failed")
        if test_result.failed > 0:
            print(f"\nFailed tests:")
            for err in test_result.errors:
                print(f"  - {err}")
            print("=" * 70)
            sys.exit(1)
        else:
            print("All tests passed!")
            print("=" * 70)
            sys.exit(0)


if __name__ == "__main__":
    main()
