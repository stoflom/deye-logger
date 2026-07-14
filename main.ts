#!/usr/bin/env -S deno run -A

const PORT = 8090;
const DB_PATH_URL = new URL("deye_solar_data.db", import.meta.url);
const DB_PATH = DB_PATH_URL.pathname; // filesystem path for python

const CONTENT_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "application/javascript",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".db": "application/octet-stream",
};

// Column labels (single source of truth)
const COLUMN_LABELS: Record<string, string> = {
  device_timestamp: "Timestamp",
  fetch_timestamp: "Fetch Time",
  inverter_sn: "Inverter SN",
  daily_energy: "Daily Energy (kWh)",
  total_energy: "Total Energy (kWh)",
  current_power: "Current Power (W)",
  battery_soc: "Battery SOC (%)",
  battery_voltage: "Battery Voltage (V)",
  battery_current: "Battery Current (A)",
  grid_power: "Grid Power (W)",
  grid_voltage: "Grid Voltage (V)",
  grid_frequency: "Grid Frequency (Hz)",
  pv1_voltage: "PV1 Voltage (V)",
  pv1_current: "PV1 Current (A)",
  pv1_power: "PV1 Power (W)",
  pv2_voltage: "PV2 Voltage (V)",
  pv2_current: "PV2 Current (A)",
  pv2_power: "PV2 Power (W)",
  load_power: "Load Power (W)",
  pv3_voltage: "PV3 Voltage (V)",
  pv3_current: "PV3 Current (A)",
  pv3_power: "PV3 Power (W)",
  total_dc_power: "Total DC Power (W)",
  total_consumption_power: "Total Consumption Power (W)",
  cumulative_consumption: "Cumulative Consumption (kWh)",
  daily_consumption: "Daily Consumption (kWh)",
  battery_power: "Battery Power (W)",
  total_charge_energy: "Total Charge Energy (kWh)",
  total_discharge_energy: "Total Discharge Energy (kWh)",
  daily_charging_energy: "Daily Charging Energy (kWh)",
  daily_discharging_energy: "Daily Discharging Energy (kWh)",
  cumulative_grid_feed_in: "Cumulative Grid Feed-in (kWh)",
  cumulative_energy_purchased: "Cumulative Energy Purchased (kWh)",
  daily_grid_feed_in: "Daily Grid Feed-in (kWh)",
  daily_energy_purchased: "Daily Energy Purchased (kWh)",
  load_voltage: "Load Voltage (V)",
  grid_current: "Grid Current (A)",
  external_ct_power: "External CT Power (W)",
  battery_rated_capacity: "Battery Rated Capacity (Ah)",
  battery_temp: "Battery Temp (°C)",
  dc_temp: "DC Temp (°C)",
  ac_temp: "AC Temp (°C)",
  generator_frequency: "Generator Frequency (Hz)",
  generator_voltage: "Generator Voltage (V)",
  total_generator_production: "Total Generator Prod. (kWh)",
  ac_voltage: "AC Voltage (V)",
  ac_current: "AC Current (A)",
  rated_power: "Rated Power (W)",
};

/** Build column list from the single COLUMN_LABELS source of truth. */
function buildColumns(): { name: string; label: string }[] {
  return Object.entries(COLUMN_LABELS).map(([name, label]) => ({ name, label }));
}

/** Get min/max dates by querying the DB via python3 (sqlite3 builtin). */
async function getDateRange(): Promise<{ min: string; max: string }> {
  const cmd = new Deno.Command("python3", {
    args: [
      "-c",
      "import sqlite3, json, sys; db=sqlite3.connect(sys.argv[1]); r=db.execute('SELECT MIN(device_timestamp), MAX(device_timestamp) FROM inverter_telemetry').fetchone(); db.close(); print(json.dumps({'min': (r[0] or '')[:10], 'max': (r[1] or '')[:10]}))",
      DB_PATH,
    ],
    stdout: "piped",
    stderr: "piped",
  });
  const { code, success, stdout, stderr } = await cmd.output();
  const output = new TextDecoder().decode(stdout).trim();
  const err = new TextDecoder().decode(stderr).trim();
  if (!success || err) {
    console.error(`getDateRange error (code=${code}):`, err || output);
    return { min: "", max: "" };
  }
  return JSON.parse(output) as { min: string; max: string };
}

async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  let pathname = url.pathname;

  // DB download
  if (pathname === "/db") {
    const file = await Deno.readFile(DB_PATH);
    return new Response(file, {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="deye_solar_data.db"',
      },
    });
  }

  // Refresh database (run deye-logger.py)
  if (pathname === "/api/refresh" && req.method === "POST") {
    const scriptPath = new URL("deye-logger.py", import.meta.url).pathname;
    const cmd = new Deno.Command("python3", {
      args: [scriptPath],
      stdin: "null",
      stdout: "piped",
      stderr: "piped",
    });
    const { code, success, stdout, stderr } = await cmd.output();

    const output = new TextDecoder().decode(stdout);
    const errOutput = new TextDecoder().decode(stderr);

    return new Response(
      JSON.stringify({ success, code, output, error: errOutput }),
      { headers: { "Content-Type": "application/json" } },
    );
  }

  // Column metadata — derived from COLUMN_LABELS map (single source of truth)
  if (pathname === "/api/columns") {
    const columns = buildColumns();
    return new Response(JSON.stringify(columns), {
      headers: { "Content-Type": "application/json" },
    });
  }

  // Dates with data (for date picker validation)
  if (pathname === "/api/dates") {
    const { min, max } = await getDateRange();
    return new Response(
      JSON.stringify({ min, max }),
      { headers: { "Content-Type": "application/json" } },
    );
  }

  // node_modules
  if (pathname.startsWith("/node_modules/")) {
    const filePath = new URL(pathname.slice(1), import.meta.url);
    try {
      const file = await Deno.readFile(filePath);
      const ext = pathname.slice(pathname.lastIndexOf("."));
      const contentType = CONTENT_TYPES[ext] ?? "application/octet-stream";
      return new Response(file, {
        headers: { "Content-Type": contentType },
      });
    } catch (err) {
      if (err instanceof Deno.errors.NotFound) {
        return new Response("Not Found", { status: 404 });
      }
      throw err;
    }
  }

  // Static file
  if (pathname === "/") pathname = "/index.html";
  const filePath = new URL(`public${pathname}`, import.meta.url);
  try {
    const file = await Deno.readFile(filePath);
    const ext = pathname.slice(pathname.lastIndexOf("."));
    const contentType = CONTENT_TYPES[ext] ?? "application/octet-stream";
    return new Response(file, {
      headers: { "Content-Type": contentType },
    });
  } catch (err) {
    if (err instanceof Deno.errors.NotFound) {
      return new Response("Not Found", { status: 404 });
    }
    throw err;
  }
}

console.log("═══════════════════════════════════════════");
console.log("  Deye Logger Viewer");
console.log(`  http://localhost:${PORT}`);
console.log("═══════════════════════════════════════════\n");

await Deno.serve({ port: PORT }, handler);
