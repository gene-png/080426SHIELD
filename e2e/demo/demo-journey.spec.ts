import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  CLIENT_EMAIL,
  CLIENT_PASSWORD,
  signIn,
} from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * SMOKE_TEST §26 (Sprint 9 T8, D-033): the post-reset hosted-demo journey,
 * driven end to end through the PRODUCTION web build.
 *
 * OPT-IN and destructive-adjacent. This spec asserts the state a fresh
 * `scripts/demo-reset.(sh|ps1) --demo` leaves behind: the hosted-demo compose
 * overlay (`docker-compose.demo.yml`) running the standalone prod web image
 * (`shield-web:demo`) against a freshly seeded Atlas story. It MUST never run
 * against a stack it did not just reset — a half-reset or dev-mode stack would
 * give misleading results — so it self-skips unless `SHIELD_DEMO_SMOKE=1`. With
 * the flag unset the default `npx playwright test` run executes ZERO tests from
 * this file and the suite's pass/fail count is unchanged (the D-033
 * opt-in-gating contract).
 *
 * To run it (destroys all local demo data — that is the point of a reset):
 *
 *   bash scripts/demo-reset.sh --demo                     # or -Demo on ps1
 *   SHIELD_DEMO_SMOKE=1 npx playwright test demo/
 *
 * The base URL resolves through helpers/baseUrl.ts exactly as the smoke suite
 * does (E2E_BASE_URL > WEB_PORT in .env > :3000), so the same demo stack the
 * reset script brought up is the one under test.
 */

test.skip(
  process.env.SHIELD_DEMO_SMOKE !== "1",
  "Hosted-demo journey — opt-in; set SHIELD_DEMO_SMOKE=1 after `scripts/demo-reset.(sh|ps1) --demo` (see the file header). Runs against the just-reset demo stack only.",
);

interface DeliverableRow {
  id: string;
  title: string;
  pdf_artifact_id: string | null;
  pdf_filename: string | null;
}

test.describe("demo-journey — hosted-demo post-reset story (SHIELD_DEMO_SMOKE=1)", () => {
  test("post-reset /ready reports the full dependency matrix all-green", async ({
    request,
  }) => {
    // The reset script already waits for this, but the spec re-asserts it as the
    // first thing it proves — a green demo journey starts from a ready backend.
    const res = await request.get(`${API_BASE}/ready`);
    expect(res.status(), "GET /ready status").toBe(200);
    const body = (await res.json()) as {
      ready: boolean;
      offenders: string[];
      checks: Record<string, { status: string; required: boolean }>;
    };
    expect(body.ready, "overall readiness").toBe(true);
    expect(body.offenders, "no required-dependency offenders").toEqual([]);
    // Required deps are ok; keycloak is dormant (OIDC flag off on the demo
    // stack) and the LLM is fixture-mode ok.
    expect(body.checks.db.status).toBe("ok");
    expect(body.checks.redis.status).toBe("ok");
    expect(body.checks.minio.status).toBe("ok");
    expect(body.checks.keycloak.status).toBe("dormant");
    expect(body.checks.llm.status).toBe("ok");
  });

  test("/sign-in serves 200 with the strict CSP (production build proof)", async ({
    page,
  }) => {
    // The demo overlay runs the PROD standalone image, not `next dev`. If that
    // image failed to build or start, this navigation would not return 200 with
    // the hardened headers — this is the prod-build health assertion.
    const response = await page.goto("/sign-in");
    expect(response, "no response for /sign-in").not.toBeNull();
    expect(response!.status(), "/sign-in status").toBe(200);

    const csp = response!.headers()["content-security-policy"];
    expect(csp, "Content-Security-Policy missing").toBeTruthy();
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");

    // The credentials form renders (the seam the demo signs in through).
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible({
      timeout: 20000,
    });
  });

  test("admin signs in through the production web build and lands on /admin", async ({
    page,
  }) => {
    test.slow();
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/");
    await page.waitForURL((url) => url.pathname.startsWith("/admin"), {
      timeout: 20000,
    });
    expect(new URL(page.url()).pathname.startsWith("/admin")).toBeTruthy();
  });

  test("seeded client signs in, sees the released-report hero, and downloads a deliverable", async ({
    page,
    request,
  }) => {
    test.slow();
    // Resolve a seeded released deliverable straight from the API so we know its
    // artifact id + §15.5 filename. The seed releases the Atlas story's
    // deliverables, so at least one carries a PDF artifact.
    const token = await adminApiToken(request);
    const clientId = await atlasClientIdViaApi(request, token);
    const listed = await request.get(
      `${API_BASE}/clients/${clientId}/deliverables`,
      {
        headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
      },
    );
    expect(
      listed.ok(),
      `list seeded deliverables (${listed.status()})`,
    ).toBeTruthy();
    const items = ((await listed.json()) as { items: DeliverableRow[] }).items;
    const seeded = items.find((d) => d.pdf_artifact_id);
    expect(
      seeded,
      "the seeded Atlas story must release at least one deliverable with a PDF",
    ).toBeTruthy();
    const deliverable = seeded as DeliverableRow;

    // The real seeded Atlas client signs in through the prod web build.
    await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);

    // /home shows the released-report hero (the tenant has released reports).
    await page.goto("/home");
    await expect(page.getByText(/report is ready/)).toBeVisible({
      timeout: 20000,
    });
    await expect(
      page.getByRole("link", { name: "View reports" }),
    ).toBeVisible();

    // /documents lists the seeded deliverable, and the client's own download
    // link streams 200 with non-zero bytes (seed → MinIO storage parity).
    await page.goto("/documents");
    await expect(page.getByRole("table")).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByRole("row").filter({ hasText: deliverable.title }),
    ).toBeVisible();

    const download = await page.request.get(
      `/api/proxy/artifacts/${deliverable.pdf_artifact_id}/download`,
    );
    expect(download.status(), "seeded deliverable download status").toBe(200);
    const bytes = await download.body();
    expect(bytes.length, "downloaded PDF byte size").toBeGreaterThan(0);
  });
});
