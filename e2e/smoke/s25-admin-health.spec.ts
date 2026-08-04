import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * SMOKE_TEST §22 (Sprint 8 T6): the /admin/health operator readiness view.
 *
 * Converts the human-runtime "Eyeball /admin/health" check (SMOKE_TEST.md:279)
 * into a spec-backed one. An admin signs in, opens /admin/health, and the
 * full-matrix operator view (HealthMatrix.tsx) reports an all-green healthy dev
 * stack:
 *   - an "All systems ready" overall badge (never the degraded/offender badge);
 *   - one row per downstream dependency — db/redis/minio (required) ok,
 *     keycloak dormant, llm (fixture-mode) ok.
 *
 * This is the same matrix HealthMatrix.test.tsx asserts against a MOCKED /ready
 * (vitest, the `pnpm -F web test` gate); here it is proven against the REAL
 * running /ready of the live dev stack, closing the human-eyeball gap.
 *
 * Read-only: it drives the admin console and touches no tenant state, so it is
 * safe anywhere in the serialized shared-DB suite.
 */

test.describe("s25 /admin/health — operator readiness matrix", () => {
  test("admin sees the full-matrix all-green operator view", async ({
    page,
  }) => {
    test.slow();
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/health");

    // The admin nav carries a System Health entry (desktop + mobile render one
    // each), and the operator page renders its heading.
    await expect(
      page.getByRole("link", { name: "System Health" }).first(),
    ).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByRole("heading", { name: "System health" }),
    ).toBeVisible({ timeout: 20000 });

    // Overall status: all-green. Every REQUIRED dependency is ok on a healthy
    // stack, so the deployment reads ready — never the degraded/offender badge.
    // The overall badge is the page's only role="status" element; the negative
    // is scoped to it because the page's descriptive copy also says "degraded".
    const overall = page.getByRole("status");
    await expect(overall).toContainText("All systems ready", {
      timeout: 20000,
    });
    await expect(overall).not.toContainText("Degraded");

    // Every dependency row renders with its healthy-stack status. The dependency
    // list is the only <ul>/<li> on the page (the sidebar nav uses bare links),
    // so a listitem filtered by the dependency name resolves exactly one row.
    const rows: Array<[string, string]> = [
      ["db", "ok"],
      ["redis", "ok"],
      ["minio", "ok"],
      ["keycloak", "dormant"],
      ["llm", "ok"],
    ];
    for (const [name, status] of rows) {
      const row = page.getByRole("listitem").filter({ hasText: name });
      await expect(row, `${name} row visible`).toBeVisible();
      await expect(row, `${name} status ${status}`).toContainText(status);
    }
  });
});
