import { defineConfig } from "@playwright/test";

// Starts a throwaway Console against an empty store in ../tmp/e2e (needs `pip install -e .[ui]` venv at ../.venv).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:7777", viewport: { width: 1440, height: 900 } },
  reporter: "list",
  webServer: {
    command:
      "rm -rf ../tmp/e2e && mkdir -p ../tmp/e2e && cd ../tmp/e2e && RUNWAY_TOKEN=devtoken RUNWAY_DEMO_DELAY=0.6 ../../.venv/bin/runway dev --no-open --port 7777",
    url: "http://127.0.0.1:7777/api/health",
    // /api/health needs no token (verified via curl); reuse if already running.
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
