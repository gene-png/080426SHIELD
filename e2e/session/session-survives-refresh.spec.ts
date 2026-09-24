/**
 * #487: a user working on ONE page must survive access-token expiry.
 *
 * The defect: a zero-argument `auth()` (every proxy route, every server
 * component) rotated the refresh token on the backend and discarded the new
 * one, so the browser kept presenting the rotated-out token. After the 60 s
 * grace window every refresh was `refresh_reused` and the user was signed out
 * -- reproduced at 15.8 minutes with the compose default 900 s access TTL. The
 * fix is `apps/web/src/middleware.ts`, which runs next-auth's middleware
 * wrapper, the form that persists the refreshed cookie.
 *
 * This spec needs a SHORT access TTL to span several expiries in minutes, so
 * it runs only in the CI step that recreates api+web with
 * `JWT_ACCESS_TTL_SECONDS=60` and sets `E2E_SESSION_TTL=1`
 * (`.github/workflows/ci.yml`, E2E job). Unlike a spec gated on a flag nothing
 * sets (#483), CI sets this one, and when it runs it PROVES the TTL is short
 * rather than trusting the flag: under the default 900 s it would pass without
 * testing anything.
 *
 * Measured locally 2026-09-23 with a 60 s TTL, using a temporary harness that
 * made 12 calls (this spec derives its own count from the TTL, 11 at 60 s):
 * with the middleware, 12 of 12 proxy calls over 4.2 minutes returned 200;
 * without it, 401 from 1.7 minutes and the session ended `reauth_required`.
 * This spec itself then passed with the fix and went red (200 then 401)
 * against a container that had not loaded it.
 */
import { expect, test } from "@playwright/test";

const ENABLED = process.env.E2E_SESSION_TTL === "1";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";

test.setTimeout(10 * 60_000);

test("proxy-only activity survives several access-token expiries", async ({
  page,
  request,
}) => {
  test.skip(
    !ENABLED,
    "needs a short access TTL -- run by CI's #487 step with E2E_SESSION_TTL=1",
  );

  // Prove the TTL is short, with a DIFFERENT user than the browser's: a second
  // login as the same user would rotate its refresh token and break the very
  // session under test.
  const probe = await request.post(`${API}/auth/login`, {
    data: { email: "client@atlas.example", password: "DemoPass!2026" },
  });
  expect(probe.ok(), `TTL probe login failed: ${probe.status()}`).toBe(true);
  // POST /auth/login returns `LoginResult`, whose pair fields are top-level.
  const expiresAt = Date.parse((await probe.json()).access_expires_at);
  const ttlSeconds = (expiresAt - Date.now()) / 1000;
  expect(
    ttlSeconds,
    `access TTL is ${Math.round(ttlSeconds)} s; this spec only tests anything under a short TTL (<= 120 s)`,
  ).toBeLessThanOrEqual(120);

  await page.goto("/sign-in");
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1500);
  await page.locator('input[type="email"]').fill("admin@kentro.example");
  await page.locator('input[type="password"]').fill("DemoPass!2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 90_000,
  });

  // Only proxy calls, no navigation and no /api/auth/session fetch: the
  // pattern of someone working in one workspace. Span at least 3 TTLs.
  const rounds = Math.ceil((3 * ttlSeconds + 30) / 20);
  const statuses: number[] = [];
  for (let i = 0; i < rounds; i++) {
    await page.waitForTimeout(20_000);
    statuses.push(
      await page.evaluate(async () => {
        const r = await fetch("/api/proxy/admin/ai-status", {
          cache: "no-store",
        });
        return r.status;
      }),
    );
  }
  expect(
    statuses.every((s) => s === 200),
    `proxy statuses: ${statuses.join(",")}`,
  ).toBe(true);

  // A session that is GONE returns `null` here, and `null?.error` is
  // undefined -- so assert the user is present, not only that no error is.
  const session = await page.evaluate(async () => {
    const r = await fetch("/api/auth/session", { cache: "no-store" });
    const j = await r.json();
    return { user: Boolean(j?.user), error: j?.error ?? null };
  });
  expect(session.user, "the session has no user -- it ended").toBe(true);
  expect(session.error, "the session ended with an error").toBeNull();
});
