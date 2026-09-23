/**
 * Signing out must sign you out, even when a response is still in flight.
 *
 * #487's first fix wrote the session cookie on EVERY matched response. A
 * response that left the server before a sign-out in another tab arrived after
 * it and put a live session cookie back -- and `POST /auth/logout` revokes
 * nothing (#392), so that restored a working session. The middleware now writes
 * the cookie only when the session actually changed (`sessionChanged` in
 * `lib/auth/session-cookie.ts`).
 *
 * Built as a regression test, not a timing measurement: Playwright HOLDS tab A's
 * proxy response until tab B has signed out, so the race is forced rather than
 * hoped for. It needs no short TTL -- within a fresh sign-in no rotation is due,
 * which is exactly the case the rotation-only rule exists for.
 */
import { expect, test } from "@playwright/test";

test.setTimeout(3 * 60_000);

test("a response that lands after sign-out does not restore the session", async ({
  browser,
}) => {
  const ctx = await browser.newContext();
  const a = await ctx.newPage();
  await a.goto("/sign-in");
  await a.waitForLoadState("networkidle").catch(() => undefined);
  await a.waitForTimeout(1500);
  await a.locator('input[type="email"]').fill("admin@kentro.example");
  await a.locator('input[type="password"]').fill("DemoPass!2026");
  await a.getByRole("button", { name: "Sign in" }).click();
  await expect(a.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 90_000,
  });

  const sessionCookies = async () =>
    (await ctx.cookies()).filter((c) => c.name.includes("session-token"));
  expect(
    (await sessionCookies()).length,
    "signed in, so a session cookie must exist before the race",
  ).toBeGreaterThan(0);

  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  let heldResponse = false;
  await a.route("**/api/proxy/admin/ai-status", async (route) => {
    const res = await route.fetch();
    heldResponse = true;
    await gate;
    await route.fulfill({ response: res });
  });
  const inflight = a.evaluate(() =>
    fetch("/api/proxy/admin/ai-status").then((r) => r.status),
  );
  await expect.poll(() => heldResponse, { timeout: 30_000 }).toBe(true);

  const b = await ctx.newPage();
  await b.goto("/admin/queue");
  await b.getByRole("button", { name: "Sign out" }).click();
  await b.waitForURL((u) => !u.pathname.startsWith("/admin"), {
    timeout: 30_000,
  });
  expect(
    (await sessionCookies()).length,
    "sign-out cleared the session cookie",
  ).toBe(0);

  release();
  await inflight;
  await a.waitForTimeout(1000);

  expect(
    (await sessionCookies()).map((c) => c.name),
    "the in-flight response put a session cookie back after sign-out",
  ).toEqual([]);
  const session = await b.evaluate(async () =>
    (await fetch("/api/auth/session", { cache: "no-store" })).json(),
  );
  expect(
    session?.user ?? null,
    "the session came back after sign-out",
  ).toBeNull();
});
