import { defineConfig } from "@playwright/test";

import base from "./playwright.config";

/**
 * Manual procedures (#483): specs that need a stack state CI does not have,
 * such as the OIDC seam switched on or a database with realistic client
 * counts. Each lives in `manual/` as `*.manual.ts`, which the default config's
 * test match never collects, so none of them can look like part of the suite.
 * Run one on purpose:
 *
 *   npx playwright test -c playwright.manual.config.ts <name>
 */
export default defineConfig({
  ...base,
  testDir: "./manual",
  testMatch: "**/*.manual.ts",
});
