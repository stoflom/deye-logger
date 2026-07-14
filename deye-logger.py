#!/usr/bin/env python3

import os
import argparse
import time
import sqlite3
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ==================== CONFIGURATION ====================
DB_NAME = os.getenv("DB_NAME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "deye_solar_data.db"))
APP_ID = os.getenv("DEYE_APP_ID")
APP_SECRET = os.getenv("DEYE_APP_SECRET")
DEYE_EMAIL = os.getenv("DEYE_EMAIL")
DEYE_PASSWORD = os.getenv("DEYE_PASSWORD")
INVERTER_SN = os.getenv("DEYE_INVERTER_SN")
BASE_URL = os.getenv("DEYE_BASE_URL", "https://eu1-developer.deyecloud.com")
GAP_THRESHOLD_MINUTES = 3
# =======================================================

if not APP_ID or not APP_SECRET or not DEYE_EMAIL or not DEYE_PASSWORD or not INVERTER_SN:
    print("Error: Missing required credentials. Copy .env.example to .env and fill in your values.")
    exit(1)

# Field mapping: DB column -> DeyeAPI key names (try in order, for realtime API)
FIELD_MAP = {
    "daily_energy": ["DailyActiveProduction"],
    "total_energy": ["TotalActiveProduction"],
    "current_power": ["InverterOutputPowerL1L2", "TotalGridPower"],
    "battery_soc": ["SOC", "BatterySoc"],
    "battery_voltage": ["BatteryVoltage"],
    "battery_current": ["BatteryCurrent"],
    "grid_power": ["TotalGridPower"],
    "grid_voltage": ["GridVoltageL1L2"],
    "grid_frequency": ["GridFrequency"],
    "pv1_voltage": ["DCVoltagePV1"],
    "pv1_current": ["DCCurrentPV1"],
    "pv1_power": ["DCPowerPV1"],
    "pv2_voltage": ["DCVoltagePV2"],
    "pv2_current": ["DCCurrentPV2"],
    "pv2_power": ["DCPowerPV2"],
    "load_power": ["UPSLoadPower"],
    "pv3_voltage": ["DCVoltagePV3"],
    "pv3_current": ["DCCurrentPV3"],
    "pv3_power": ["DCPowerPV3"],
    "total_dc_power": ["TotalDCInputPower"],
    "total_consumption_power": ["TotalConsumptionPower"],
    "cumulative_consumption": ["CumulativeConsumption"],
    "daily_consumption": ["DailyConsumption"],
    "battery_power": ["BatteryPower"],
    "total_charge_energy": ["TotalChargeEnergy"],
    "total_discharge_energy": ["TotalDischargeEnergy"],
    "daily_charging_energy": ["DailyChargingEnergy"],
    "daily_discharging_energy": ["DailyDischargingEnergy"],
    "cumulative_grid_feed_in": ["CumulativeGridFeedIn"],
    "cumulative_energy_purchased": ["CumulativeEnergyPurchased"],
    "daily_grid_feed_in": ["DailyGridFeedIn"],
    "daily_energy_purchased": ["DailyEnergyPurchased"],
    "load_voltage": ["LoadVoltageL1L2"],
    "grid_current": ["GridCurrentL1L2"],
    "external_ct_power": ["ExternalCTPowerL1L2"],
    "battery_rated_capacity": ["BatteryRatedCapacity"],
    "battery_temp": ["Temperature- Battery"],
    "dc_temp": ["DC Temperature"],
    "ac_temp": ["AC Temperature"],
    "generator_frequency": ["GeneratorFrequency"],
    "generator_voltage": ["GenVoltage"],
    "total_generator_production": ["TotalGeneratorProduction"],
    "ac_voltage": ["ACVoltageRUA"],
    "ac_current": ["ACCurrentRUA"],
    "rated_power": ["RatedPower"],
}

# Measure point names used in the history API (granularity=1 intraday)
# Retrieved from /v1.0/device/measurePoints endpoint
# API limit: max 5 measure points per call
HISTORY_MEASURE_POINT_BATCHES = [
    ["DailyActiveProduction",   # -> daily_energy
     "TotalActiveProduction",   # -> total_energy
     "InverterOutputPowerL1L2", # -> current_power
     "SOC",                     # -> battery_soc
     "BatteryVoltage"],         # -> battery_voltage
    ["BatteryCurrent",          # -> battery_current
     "TotalGridPower",          # -> grid_power
     "GridVoltageL1L2",         # -> grid_voltage
     "GridFrequency",           # -> grid_frequency
     "DCPowerPV2"],             # -> pv2_power
    ["DCVoltagePV1",            # -> pv1_voltage
     "DCCurrentPV1",            # -> pv1_current
     "DCPowerPV1",              # -> pv1_power
     "DCVoltagePV2",            # -> pv2_voltage
     "DCCurrentPV2"],           # -> pv2_current
    ["UPSLoadPower",            # -> load_power
     "DCVoltagePV3",            # -> pv3_voltage
     "DCCurrentPV3",            # -> pv3_current
     "DCPowerPV3",              # -> pv3_power
     "TotalDCInputPower"],      # -> total_dc_power
    ["TotalConsumptionPower",   # -> total_consumption_power
     "CumulativeConsumption",   # -> cumulative_consumption
     "DailyConsumption",        # -> daily_consumption
     "BatteryPower",            # -> battery_power
     "TotalChargeEnergy"],      # -> total_charge_energy
    ["TotalDischargeEnergy",    # -> total_discharge_energy
     "DailyChargingEnergy",     # -> daily_charging_energy
     "DailyDischargingEnergy",  # -> daily_discharging_energy
     "CumulativeGridFeedIn",    # -> cumulative_grid_feed_in
     "CumulativeEnergyPurchased"], # -> cumulative_energy_purchased
    ["DailyGridFeedIn",         # -> daily_grid_feed_in
     "DailyEnergyPurchased",    # -> daily_energy_purchased
     "LoadVoltageL1L2",         # -> load_voltage
     "GridCurrentL1L2",         # -> grid_current
     "ExternalCTPowerL1L2"],    # -> external_ct_power
    ["BatteryRatedCapacity",    # -> battery_rated_capacity
     "Temperature- Battery",    # -> battery_temp
     "DC Temperature",          # -> dc_temp
     "AC Temperature",          # -> ac_temp
     "RatedPower"],             # -> rated_power
    ["GeneratorFrequency",      # -> generator_frequency
     "GenVoltage",              # -> generator_voltage
     "TotalGeneratorProduction",# -> total_generator_production
     "ACVoltageRUA",            # -> ac_voltage
     "ACCurrentRUA"],           # -> ac_current
]

# History API measure point name -> DB column mapping
HISTORY_FIELD_MAP = {
    "DailyActiveProduction": "daily_energy",
    "TotalActiveProduction": "total_energy",
    "InverterOutputPowerL1L2": "current_power",
    "SOC": "battery_soc",
    "BatteryVoltage": "battery_voltage",
    "BatteryCurrent": "battery_current",
    "TotalGridPower": "grid_power",
    "GridVoltageL1L2": "grid_voltage",
    "GridFrequency": "grid_frequency",
    "DCVoltagePV1": "pv1_voltage",
    "DCCurrentPV1": "pv1_current",
    "DCPowerPV1": "pv1_power",
    "DCVoltagePV2": "pv2_voltage",
    "DCCurrentPV2": "pv2_current",
    "DCPowerPV2": "pv2_power",
    "UPSLoadPower": "load_power",
    "DCVoltagePV3": "pv3_voltage",
    "DCCurrentPV3": "pv3_current",
    "DCPowerPV3": "pv3_power",
    "TotalDCInputPower": "total_dc_power",
    "TotalConsumptionPower": "total_consumption_power",
    "CumulativeConsumption": "cumulative_consumption",
    "DailyConsumption": "daily_consumption",
    "BatteryPower": "battery_power",
    "TotalChargeEnergy": "total_charge_energy",
    "TotalDischargeEnergy": "total_discharge_energy",
    "DailyChargingEnergy": "daily_charging_energy",
    "DailyDischargingEnergy": "daily_discharging_energy",
    "CumulativeGridFeedIn": "cumulative_grid_feed_in",
    "CumulativeEnergyPurchased": "cumulative_energy_purchased",
    "DailyGridFeedIn": "daily_grid_feed_in",
    "DailyEnergyPurchased": "daily_energy_purchased",
    "LoadVoltageL1L2": "load_voltage",
    "GridCurrentL1L2": "grid_current",
    "ExternalCTPowerL1L2": "external_ct_power",
    "BatteryRatedCapacity": "battery_rated_capacity",
    "Temperature- Battery": "battery_temp",
    "DC Temperature": "dc_temp",
    "AC Temperature": "ac_temp",
    "GeneratorFrequency": "generator_frequency",
    "GenVoltage": "generator_voltage",
    "TotalGeneratorProduction": "total_generator_production",
    "ACVoltageRUA": "ac_voltage",
    "ACCurrentRUA": "ac_current",
    "RatedPower": "rated_power",
}

def init_database():
    """Sets up SQLite schema with explicit timestamp index for fast gap checking."""
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inverter_telemetry (
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
            pv3_voltage REAL,
            pv3_current REAL,
            pv3_power REAL,
            total_dc_power REAL,
            total_consumption_power REAL,
            cumulative_consumption REAL,
            daily_consumption REAL,
            battery_power REAL,
            total_charge_energy REAL,
            total_discharge_energy REAL,
            daily_charging_energy REAL,
            daily_discharging_energy REAL,
            cumulative_grid_feed_in REAL,
            cumulative_energy_purchased REAL,
            daily_grid_feed_in REAL,
            daily_energy_purchased REAL,
            load_voltage REAL,
            grid_current REAL,
            external_ct_power REAL,
            battery_rated_capacity REAL,
            battery_temp REAL,
            dc_temp REAL,
            ac_temp REAL,
            generator_frequency REAL,
            generator_voltage REAL,
            total_generator_production REAL,
            ac_voltage REAL,
            ac_current REAL,
            rated_power REAL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON inverter_telemetry(device_timestamp)')
    # Migration tracking table
    cursor.execute('CREATE TABLE IF NOT EXISTS _schema_migrations (key TEXT PRIMARY KEY, done INTEGER DEFAULT 1)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gap_attempts (
            gap_start TEXT,
            gap_end TEXT,
            attempted_at TEXT,
            records_imported INTEGER DEFAULT 0,
            PRIMARY KEY (gap_start, gap_end)
        )
    ''')
    # Migrate existing databases: add columns if missing
    for col in ["pv1_voltage", "pv1_current", "pv1_power", "pv2_voltage", "pv2_current", "pv2_power", "load_power",
                "pv3_voltage", "pv3_current", "pv3_power", "total_dc_power",
                "total_consumption_power", "cumulative_consumption", "daily_consumption",
                "battery_power", "total_charge_energy", "total_discharge_energy",
                "daily_charging_energy", "daily_discharging_energy",
                "cumulative_grid_feed_in", "cumulative_energy_purchased",
                "daily_grid_feed_in", "daily_energy_purchased",
                "load_voltage", "grid_current", "external_ct_power",
                "battery_rated_capacity", "battery_temp", "dc_temp", "ac_temp",
                "generator_frequency", "generator_voltage", "total_generator_production",
                "ac_voltage", "ac_current", "rated_power"]:
        try:
            cursor.execute(f"ALTER TABLE inverter_telemetry ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass  # column already exists

    # Sort rows by device_timestamp if not already ordered (one-time migration)
    cursor.execute("SELECT 1 FROM _schema_migrations WHERE key = 'telemetry_sorted'")
    if cursor.fetchone() is None:
        cursor.execute("SELECT COUNT(*) FROM inverter_telemetry")
        count = cursor.fetchone()[0]
        if count > 0:
            cursor.execute("SELECT device_timestamp FROM inverter_telemetry WHERE rowid = (SELECT MIN(rowid) FROM inverter_telemetry)")
            first_row = cursor.fetchone()[0]
            cursor.execute("SELECT MIN(device_timestamp) FROM inverter_telemetry")
            min_ts = cursor.fetchone()[0]
            if first_row != min_ts:
                print("  Reordering telemetry table by measurement time...")
                cursor.execute("SELECT sql FROM sqlite_master WHERE name='inverter_telemetry' AND type='table'")
                ddl = cursor.fetchone()[0]
                new_ddl = ddl.replace("inverter_telemetry", "inverter_telemetry_sorted")
                cursor.executescript(new_ddl)
                cursor.execute("INSERT INTO inverter_telemetry_sorted SELECT * FROM inverter_telemetry ORDER BY device_timestamp")
                cursor.execute("DROP TABLE inverter_telemetry")
                cursor.execute("ALTER TABLE inverter_telemetry_sorted RENAME TO inverter_telemetry")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON inverter_telemetry(device_timestamp)")
                print(f"  ✅ Table reordered ({count} rows).")
            cursor.execute("INSERT OR IGNORE INTO _schema_migrations (key) VALUES ('telemetry_sorted')")

    # Clean gap_attempts — all historical gaps have been resolved (one-time migration)
    cursor.execute("SELECT 1 FROM _schema_migrations WHERE key = 'gap_attempts_cleared'")
    if cursor.fetchone() is None:
        cursor.execute("SELECT COUNT(*) FROM gap_attempts")
        gap_count = cursor.fetchone()[0]
        if gap_count > 0:
            cursor.execute("DELETE FROM gap_attempts")
            print(f"  🧹 Cleared {gap_count} stale gap attempt records.")
        cursor.execute("INSERT OR IGNORE INTO _schema_migrations (key) VALUES ('gap_attempts_cleared')")

    conn.commit()
    conn.close()

def gap_already_attempted(gap_start, gap_end):
    """Returns True if this exact gap was already attempted for backfill."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM gap_attempts WHERE gap_start = ? AND gap_end = ?", (gap_start, gap_end))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def record_gap_attempt(gap_start, gap_end, records_imported):
    """Records a backfill attempt so the gap is not retried."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO gap_attempts (gap_start, gap_end, attempted_at, records_imported)
        VALUES (?, ?, ?, ?)
    ''', (gap_start, gap_end, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), records_imported))
    conn.commit()
    conn.close()

def get_access_token():
    """Authenticates with Deye OpenAPI using email + password."""
    url = f"{BASE_URL}/v1.0/account/token?appId={APP_ID}"

    try:
        response = requests.post(url, json={
            "appSecret": APP_SECRET,
            "email": DEYE_EMAIL,
            "password": DEYE_PASSWORD,
        }, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == "1000000":
            return data.get("accessToken") or data.get("data", {}).get("accessToken")
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def parse_device_data(device):
    """Converts DeyeAPI key-value dataList into a flat dict for saving."""
    raw_data = device.get("dataList", [])
    kv = {}
    for item in raw_data:
        kv[item["key"]] = float(item["value"]) if item["value"] else 0.0

    record = {
        "device_timestamp": datetime.fromtimestamp(device.get("collectionTime", 0)).strftime('%Y-%m-%d %H:%M:%S'),
        "inverter_sn": device.get("deviceSn", INVERTER_SN),
    }

    for col, keys in FIELD_MAP.items():
        for k in keys:
            if k in kv:
                record[col] = kv[k]
                break
        else:
            record[col] = 0.0

    return record

def fetch_latest_data(token):
    """Fetches the latest telemetry from DeyeCloud."""
    url = f"{BASE_URL}/v1.0/device/latest"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(url, json={"deviceList": [INVERTER_SN]}, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == "1000000":
            devices = data.get("deviceDataList", [])
            for d in devices:
                if d.get("deviceSn") == INVERTER_SN:
                    return parse_device_data(d)
        return None
    except Exception as e:
        print(f"Latest data fetch error: {e}")
        return None

def fetch_historical_range(token, start_date, end_date):
    """Queries Deye's history endpoint for intraday data in a date range.

    Batches measure points across multiple calls (API limit: 5 per call).
    Both start_date and end_date are datetime.date objects.

    The Deye history API caps at ~1440 data points per call (1 day at 1-min granularity),
    so we iterate day-by-day to ensure complete coverage.
    """
    url = f"{BASE_URL}/v1.0/device/history"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_entries = {}  # timestamp -> merged entry dict

    current = start_date
    while current < end_date:
        day_end = current + timedelta(days=1)
        for batch in HISTORY_MEASURE_POINT_BATCHES:
            payload = {
                "deviceSn": INVERTER_SN,
                "granularity": 1,
                "startAt": current.strftime("%Y-%m-%d"),
                "endAt": day_end.strftime("%Y-%m-%d"),
                "measurePoints": batch,
            }
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                res_data = response.json()
                if res_data.get("code") != "1000000":
                    print(f"  API error for batch {batch} on {current}: {res_data.get('msg')}")
                    continue
                for entry in res_data.get("dataList", []):
                    ts = entry.get("time")
                    if ts not in all_entries:
                        all_entries[ts] = entry
                    else:
                        existing = {i["key"] for i in all_entries[ts].get("itemList", [])}
                        for item in entry.get("itemList", []):
                            if item["key"] not in existing:
                                all_entries[ts]["itemList"].append(item)
            except Exception as e:
                print(f"  Failed pulling historical window for {current}: {e}")
        current = day_end

    # Return sorted by timestamp
    return [all_entries[k] for k in sorted(all_entries.keys(), key=int)]

def save_records(records):
    """Saves a list of parsed telemetry records into SQLite."""
    if not records:
        return 0

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    inserted_count = 0
    fetch_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for item in records:
        device_time = item.get("device_timestamp")
        if not device_time:
            continue

        try:
            data_cols = [
                "daily_energy", "total_energy", "current_power", "battery_soc",
                "battery_voltage", "battery_current", "grid_power", "grid_voltage", "grid_frequency",
                "pv1_voltage", "pv1_current", "pv1_power", "pv2_voltage", "pv2_current", "pv2_power",
                "load_power", "pv3_voltage", "pv3_current", "pv3_power", "total_dc_power",
                "total_consumption_power", "cumulative_consumption", "daily_consumption",
                "battery_power", "total_charge_energy", "total_discharge_energy",
                "daily_charging_energy", "daily_discharging_energy",
                "cumulative_grid_feed_in", "cumulative_energy_purchased",
                "daily_grid_feed_in", "daily_energy_purchased",
                "load_voltage", "grid_current", "external_ct_power",
                "battery_rated_capacity", "battery_temp", "dc_temp", "ac_temp",
                "generator_frequency", "generator_voltage", "total_generator_production",
                "ac_voltage", "ac_current", "rated_power",
            ]
            placeholders = ", ".join(["?"] * (3 + len(data_cols)))
            cols_str = "device_timestamp, fetch_timestamp, inverter_sn, " + ", ".join(data_cols)
            values = (device_time, fetch_time, item.get("inverter_sn", INVERTER_SN)) + \
                     tuple(item.get(c, 0.0) for c in data_cols)
            cursor.execute(f'''
                INSERT OR IGNORE INTO inverter_telemetry
                ({cols_str})
                VALUES ({placeholders})
            ''', values)
            if cursor.rowcount > 0:
                inserted_count += 1
        except sqlite3.Error:
            continue

    conn.commit()
    conn.close()
    return inserted_count

def parse_history_response(history_data):
    """Converts /v1.0/device/history granularity=1 response into flat records.

    Response format:
      { "dataList": [ { "time": "epoch_seconds", "itemList": [ {"key": ..., "value": ..., "unit": ...} ] } ] }
    """
    if not history_data:
        return []

    records = []
    for entry in history_data:
        ts = entry.get("time")
        if not ts:
            continue

        device_time = datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
        record = {
            "device_timestamp": device_time,
            "inverter_sn": INVERTER_SN,
        }

        for item in entry.get("itemList", []):
            key = item.get("key")
            value = item.get("value")
            if key in HISTORY_FIELD_MAP:
                record[HISTORY_FIELD_MAP[key]] = float(value) if value else 0.0

        records.append(record)

    return records

def format_duration(delta):
    """Formats a timedelta into a human-readable string."""
    total_minutes = int(delta.total_seconds() // 60)
    days = total_minutes // 1440
    hours = (total_minutes % 1440) // 60
    minutes = total_minutes % 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)

def scan_and_fix_time_gaps(token, gap_threshold_minutes=GAP_THRESHOLD_MINUTES):
    """Finds periods missing data and executes historical backfills.

    Groups gaps by day so that each day's data is fetched from the API only once,
    even if multiple gaps exist within the same day.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT device_timestamp FROM inverter_telemetry ORDER BY device_timestamp ASC")
    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return 0

    print("Analyzing timeline records for telemetry gaps...")

    # Collect all gaps
    gaps = []
    for i in range(len(rows) - 1):
        try:
            t1 = datetime.strptime(rows[i][0], '%Y-%m-%d %H:%M:%S')
            t2 = datetime.strptime(rows[i+1][0], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue

        gap = t2 - t1
        if gap > timedelta(minutes=gap_threshold_minutes):
            gap_start = t1.strftime('%Y-%m-%d %H:%M:%S')
            gap_end = t2.strftime('%Y-%m-%d %H:%M:%S')

            if gap_already_attempted(gap_start, gap_end):
                print(f"  ⏭️ Skipping already-attempted gap: {gap_start} -> {gap_end} ({format_duration(gap)})")
                continue

            print(f"  ⚠️ Found data gap: {gap_start} -> {gap_end} ({format_duration(gap)})")
            gaps.append((t1, t2, gap_start, gap_end))

    if not gaps:
        return 0

    # Group gaps by the set of days they span
    day_gaps = {}  # frozenset of dates -> list of (t1, t2, gap_start, gap_end)
    for t1, t2, gap_start, gap_end in gaps:
        days = set()
        current = t1.date()
        while current <= t2.date():
            days.add(current)
            current += timedelta(days=1)
        key = frozenset(days)
        day_gaps.setdefault(key, []).append((t1, t2, gap_start, gap_end))

    total_recovered = 0

    for days, gap_list in day_gaps.items():
        sorted_days = sorted(days)
        start_date = sorted_days[0]
        end_date = sorted_days[-1] + timedelta(days=1)

        days_label = ", ".join(d.strftime('%Y-%m-%d') for d in sorted_days)
        print(f"  Querying gap data for: {days_label} ({len(gap_list)} gap(s))")

        history_data = fetch_historical_range(token, start_date, end_date)
        if not history_data:
            print(f"  ⚠️ History API returned no data for {days_label}.")
            for _, _, gap_start, gap_end in gap_list:
                print(f"  ℹ️  Marking gap {gap_start} -> {gap_end} as no-data.")
                record_gap_attempt(gap_start, gap_end, 0)
            continue

        records = parse_history_response(history_data)
        if not records:
            print(f"  ⚠️ No records parsed from history API response for {days_label}.")
            for _, _, gap_start, gap_end in gap_list:
                print(f"  ℹ️  Marking gap {gap_start} -> {gap_end} as no-data.")
                record_gap_attempt(gap_start, gap_end, 0)
            continue

        day_recovered = save_records(records)
        total_recovered += day_recovered

        if day_recovered > 0:
            print(f"  ✅ Imported {day_recovered} records for {days_label}.")
            for _, _, gap_start, gap_end in gap_list:
                record_gap_attempt(gap_start, gap_end, day_recovered)
        else:
            print(f"  ⚠️ Backfill returned 0 new records for {days_label} (API may not have data).")
            for _, _, gap_start, gap_end in gap_list:
                print(f"  ℹ️  Marking gap {gap_start} -> {gap_end} as no-data.")
                record_gap_attempt(gap_start, gap_end, 0)

        time.sleep(1)

    return total_recovered

def parse_date(date_str):
    """Parse a date string in multiple formats, returning a datetime at 00:00."""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(hour=0, minute=0, second=0)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: '{date_str}'. Supported formats: YYYY-MM-DD, DD Mon YYYY, DD MMMM YYYY, etc.")

def fetch_since(token, since_dt):
    """Fetches all historical data from since_dt up to now, inserting into DB.

    Designed for initial data loads. Splits large ranges into 7-day chunks to
    stay within API limits. INSERT OR IGNORE handles duplicates gracefully.
    """
    init_database()
    end_dt = datetime.now()
    chunk_size = timedelta(days=7)

    current_start = since_dt
    total_fetched = 0
    total_inserted = 0

    while current_start < end_dt:
        chunk_end = min(current_start + chunk_size, end_dt)
        chunk_label = f"{current_start.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}"
        print(f"  Chunk: {chunk_label}")

        history_data = fetch_historical_range(token, current_start.date(), chunk_end.date())
        if history_data:
            records = parse_history_response(history_data)
            if records:
                inserted = save_records(records)
                total_fetched += len(records)
                total_inserted += inserted
                print(f"    Fetched {len(records)}, inserted {inserted}")
        else:
            print(f"    No data returned")

        current_start = chunk_end
        time.sleep(0.5)  # polite rate-limiting between chunks

    if total_inserted == 0:
        print(f"  No new data found. Total fetched: {total_fetched}, new records inserted: {total_inserted}")
    else:
        print(f"  ✅ Done. Total fetched: {total_fetched}, new records inserted: {total_inserted}")
    return total_fetched, total_inserted

def main():
    parser = argparse.ArgumentParser(
        description="Deye Solar Inverter Logger — fetches telemetry from DeyeCloud into a local SQLite database. "
                    "On each run, detects time gaps in stored data and automatically backfills them "
                    "from the history API. Gaps with no available data are marked as attempted and not retried.")
    parser.add_argument("--fetch-since", type=str, help="Bulk import historical data from the given date up to now (e.g. '27 May 2026'). "
                        "Splits into 7-day chunks to respect API limits.")
    parser.add_argument("-g", "--gap", type=int, default=GAP_THRESHOLD_MINUTES,
                        help=f"Minimum gap duration in minutes to trigger backfill (default: {GAP_THRESHOLD_MINUTES})")
    args = parser.parse_args()

    init_database()
    token = get_access_token()
    if not token:
        print("Failed to acquire access token.")
        return

    if args.fetch_since:
        try:
            since_dt = parse_date(args.fetch_since)
        except ValueError as e:
            print(f"Error: {e}")
            return
        fetch_since(token, since_dt)
        return

    print(f"Fetching latest telemetry... (gap threshold: {args.gap} min)")
    total_new = 0
    latest = fetch_latest_data(token)
    if latest:
        new_entry = save_records([latest])
        total_new += new_entry
        if new_entry:
            print(f"  ✅ Captured telemetry at {latest['device_timestamp']}.")
            print(f"     Grid: {latest['grid_power']:>7.0f} W | Load: {latest['load_power']:>7.0f} W | Solar: {latest['total_dc_power']:>7.0f} W")
            print(f"     Daily: {latest['daily_energy']:>7.1f} kWh | Total: {latest['total_energy']:>7.1f} kWh | Inv: {latest['current_power']:>7.0f} W")
        else:
            print("  ℹ️  No new data - record already exists in database.")
    else:
        print("  ❌ No data returned from API.")

    total_new += scan_and_fix_time_gaps(token, args.gap)

    if total_new == 0:
        print("No new data found.")
    else:
        print(f"Done. New records inserted: {total_new}")

if __name__ == "__main__":
    main()
