#!/usr/bin/env python3
"""Robustness & raw-capture tests for deye-logger.py (design §12.3).

Self-contained: sets dummy credentials, uses a temporary database, and never
touches the real .env or the production database. Verifies that ingestion is
robust to the non-numeric / unknown fields returned by the Deye Cloud API and
that every field is captured losslessly into telemetry_raw.

Run with:
    python3 deye-cloud/test/test_data_capture.py
"""
import os
import sys
import tempfile
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "deye-logger.py"))

# Dummy credentials so the module-level credential check passes on import.
# load_dotenv() does not override existing env vars, so these win over .env.
for var in ("DEYE_APP_ID", "DEYE_APP_SECRET", "DEYE_EMAIL", "DEYE_PASSWORD", "DEYE_INVERTER_SN"):
    os.environ.setdefault(var, "test")

# Load the ingestion functions without running the pipeline.
ns = {"__file__": SCRIPT}
with open(SCRIPT) as f:
    src = f.read().split('if __name__')[0]
exec(compile(src, SCRIPT, "exec"), ns)

_to_number = ns["_to_number"]
_is_numeric = ns["_is_numeric"]
parse_device_data = ns["parse_device_data"]
parse_history_response = ns["parse_history_response"]
save_records = ns["save_records"]
init_database = ns["init_database"]

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        print(f"  PASS: {name}")
        PASSED += 1
    else:
        print(f"  FAIL: {name} {detail}")
        FAILED += 1


def test_to_number():
    print("--- Test 1: _to_number() conversion ---")
    check("int -> float", _to_number(3) == 3.0)
    check("float -> float", _to_number(2.5) == 2.5)
    check("numeric string", _to_number("16000.00") == 16000.0)
    check("zero string", _to_number("0") == 0.0)
    check("negative string", _to_number("-2.10") == -2.1)
    check("non-numeric string -> None", _to_number("9028-1727") is None)
    check("HMI string -> None", _to_number("0000-C381") is None)
    check("empty string -> None", _to_number("") is None)
    check("None -> None", _to_number(None) is None)
    check("bool -> None", _to_number(True) is None)
    check("_is_numeric('9028-1727') is False", _is_numeric("9028-1727") is False)
    check("_is_numeric('1.5') is True", _is_numeric("1.5") is True)


def test_parse_device_data():
    print("--- Test 2: parse_device_data() with non-numeric fields ---")
    device = {
        "deviceSn": "TEST123",
        "collectionTime": 1789638171,
        "dataList": [
            {"key": "SOC", "value": "100"},
            {"key": "BatteryVoltage", "value": "54.44"},
            {"key": "MAIN", "value": "9028-1727"},
            {"key": "HMI", "value": "0000-C381"},
            {"key": "UnknownField", "value": "42.5"},
        ],
    }
    try:
        rec = parse_device_data(device)
        check("parses without error", True)
    except Exception as e:
        check("parses without error", False, f"raised {type(e).__name__}: {e}")
        return

    check("known numeric SOC", rec.get("battery_soc") == 100.0, f"got {rec.get('battery_soc')}")
    check("known numeric BatteryVoltage", rec.get("battery_voltage") == 54.44, f"got {rec.get('battery_voltage')}")
    check("unmapped known column is None", rec.get("rated_power") is None)

    raw = rec.get("raw", {})
    check("raw captures MAIN", raw.get("MAIN") == "9028-1727", f"got {raw.get('MAIN')}")
    check("raw captures HMI", raw.get("HMI") == "0000-C381")
    check("raw captures unknown field", raw.get("UnknownField") == "42.5")


def test_parse_history_response():
    print("--- Test 3: parse_history_response() with non-numeric fields ---")
    history = [
        {
            "time": "1789638171",
            "itemList": [
                {"key": "SOC", "value": "99", "unit": "%"},
                {"key": "MAIN", "value": "9028-1727"},
                {"key": "HMI", "value": "0000-C381"},
            ],
        }
    ]
    try:
        recs = parse_history_response(history)
        check("parses without error", True)
    except Exception as e:
        check("parses without error", False, f"raised {type(e).__name__}: {e}")
        return

    check("one record parsed", len(recs) == 1, f"got {len(recs)}")
    if not recs:
        return
    rec = recs[0]
    check("known numeric SOC", rec.get("battery_soc") == 99.0, f"got {rec.get('battery_soc')}")
    raw = rec.get("raw", {})
    check("raw captures MAIN", raw.get("MAIN") == "9028-1727")
    check("raw captures HMI", raw.get("HMI") == "0000-C381")


def test_save_records_raw_capture():
    print("--- Test 4: save_records() raw capture -> telemetry_raw ---")
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        ns["DB_NAME"] = db_path
        init_database()

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_raw'")
        check("telemetry_raw table created", cur.fetchone() is not None)
        conn.close()

        record = parse_device_data({
            "deviceSn": "TEST123",
            "collectionTime": 1789638171,
            "dataList": [
                {"key": "SOC", "value": "100"},
                {"key": "BatteryVoltage", "value": "54.44"},
                {"key": "MAIN", "value": "9028-1727"},
                {"key": "HMI", "value": "0000-C381"},
            ],
        })
        n = save_records([record])
        check("inverter_telemetry row inserted", n == 1, f"got {n}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        ts = record["device_timestamp"]

        cur.execute(
            "SELECT battery_soc, battery_voltage FROM inverter_telemetry WHERE device_timestamp=?",
            (ts,))
        row = cur.fetchone()
        check("inverter_telemetry values", row is not None and row[0] == 100.0 and row[1] == 54.44,
              f"got {row}")

        cur.execute("SELECT api_key, value, is_numeric FROM telemetry_raw WHERE device_timestamp=?", (ts,))
        raw_rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        check("telemetry_raw MAIN (non-numeric)", raw_rows.get("MAIN") == ("9028-1727", 0),
              f"got {raw_rows.get('MAIN')}")
        check("telemetry_raw HMI (non-numeric)", raw_rows.get("HMI") == ("0000-C381", 0))
        check("telemetry_raw SOC (numeric)", raw_rows.get("SOC") == ("100", 1),
              f"got {raw_rows.get('SOC')}")
        check("telemetry_raw captured all 4 fields", len(raw_rows) == 4, f"got {len(raw_rows)}")
        conn.close()
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def main():
    print("=" * 48)
    print("Deye Cloud — Robustness & Raw-Capture Tests")
    print("=" * 48)
    test_to_number()
    test_parse_device_data()
    test_parse_history_response()
    test_save_records_raw_capture()
    print()
    print("=" * 48)
    print(f"Results: {PASSED} passed, {FAILED} failed")
    print("=" * 48)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
