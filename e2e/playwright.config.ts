import { defineConfig, devices } from "@playwright/test";
import { resolveBaseUrl } from "./helpers/baseUrl";

/**
 * SHIELD smoke-test config. Specs run on the HOST against the Docker stack's
 * web app — canonically http://localhost:3000; override with E2E_BASE_URL or
 * a WEB_PORT line in the repo-root .env (see helpers/baseUrl.ts). The specs
 * share one seeded database, so they must not run in parallel
 * (fullyParallel: false, single worker) to keep DB-mutating flows
 * deterministic.
 */
export default defineConfig({
  testDir: ".",
  // Next.js dev compiles routes on first hit; give flows room for cold compiles.
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: resolveBaseUrl(),
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
