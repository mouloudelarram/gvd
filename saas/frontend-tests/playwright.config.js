// @ts-check
const { defineConfig, devices } = require("@playwright/test");

/**
 * Playwright configuration for GVD web-UI accessibility + journey tests.
 *
 * The `webServer` block boots the real Flask app (rendering real templates,
 * CSS and JS) so axe-core assertions run against production markup — not a
 * mock. It only exercises **unauthenticated** pages (login + OAuth error) so
 * no GitHub credentials or live OAuth are required. Authenticated journeys
 * (dashboard, scan modal, bulk scan) need an OAuth mock and are tracked as a
 * follow-up (see README.md).
 */
module.exports = defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    // Launch the real app from the parent (saas) directory.
    // Use "py" on Windows where the Python Launcher is the entrypoint; fall back
    // to "python3" on Linux/macOS (CI). The PYTHON env var can override both.
    command: process.env.PYTHON ? `${process.env.PYTHON} app.py` : (process.platform === "win32" ? "py app.py" : "python3 app.py"),
    cwd: "..",
    url: "http://127.0.0.1:5000/health",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      // Dummy values: the app validates these at import time but the
      // unauthenticated pages never perform a real token exchange.
      GITHUB_CLIENT_ID: "test_client_id",
      GITHUB_CLIENT_SECRET: "test_client_secret",
      FLASK_SECRET_KEY: "test_secret_key_for_ci_only_not_a_real_secret",
      OAUTH_REDIRECT_URI: "http://127.0.0.1:5000/callback",
      FLASK_ENV: "development",
    },
  },
});

