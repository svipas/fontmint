// End-to-end tests against the production build: bun run build, then bun run e2e.
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  // Pyodide starts in each worker; a slow CI machine needs more than the default 30 s.
  timeout: 90_000,
  expect: { timeout: 30_000 },
  use: { baseURL: `http://localhost:${PORT}/fontmint/`, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  ],
  webServer: {
    command: "bun scripts/serve.ts",
    env: { PORT: String(PORT) },
    url: `http://localhost:${PORT}/fontmint/`,
    reuseExistingServer: !process.env.CI,
  },
});
