/**
 * pm2 process definition for deye-logger (production, e.g. fedora-nuc).
 *
 * pm2 supervises backend/start.sh, which:
 *   1. bundles the frontend with esbuild, and
 *   2. runs the Deno server (port 8090) against the project-root SQLite db.
 * The Python fetcher (deye-cloud/deye-logger.py) is a one-shot cron job — it
 * is NOT part of this config (see README "Scheduled Runs").
 *
 * IMPORTANT: keep `watch: false`. start.sh rebuilds frontend/public/app.js
 * on every start; with watch enabled, that file change triggers a pm2
 * restart, which rebuilds again — an infinite restart loop that takes the
 * server down for a few seconds every minute. (This exact loop bit the
 * trees project; see TreesBackend/ecosystem.config.cjs.)
 *
 * Production start:
 *
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 */
module.exports = {
  apps: [
    {
      name: 'deye-logger',
      cwd: __dirname,
      script: 'backend/start.sh',
      // 'none' execs start.sh directly (shebang) instead of via node.
      interpreter: 'none',
      // Bind all interfaces so the viewer is reachable on the LAN;
      // drop -H (or set -H localhost) for local-only access.
      args: '-H 0.0.0.0',
      // The whole point of the fix: never restart on file changes.
      watch: false,
      autorestart: true,
      // Deno + SQLite stay well below this; guards against a real leak.
      max_memory_restart: '512M',
      env: {},
    },
  ],
};
