import { expect, type Page } from "@playwright/test";

/**
 * Demo credentials seeded by scripts/seed_demo.py / dev-up.
 * Admin is a Kentro consultant; client belongs to the Atlas tenant.
 */
export const ADMIN_EMAIL = "admin@kentro.example";
export const ADMIN_PASSWORD = "DemoPass!2026";
export const CLIENT_EMAIL = "client@atlas.example";
export const CLIENT_PASSWORD = "DemoPass!2026";

/**
 * A unique email for a throwaway registration, so re-runs never collide on the
 * duplicate-email guard. Self-registration is open (D-034): any domain is
 * accepted and the tenant is auto-provisioned, so no approved client_domain row
 * is required. A brand-new company domain provisions its own org.
 */
export function uniqueEmail(domain = "atlas.example"): string {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return `qa+${stamp}@${domain}`;
}

/**
 * Give the App Router client bundle time to hydrate before interacting. Until
 * React attaches, a submit-button click triggers a native form submit that
 * reloads the page and drops the typed values. networkidle plus a short settle
 * is a reliable-enough signal in Next.js dev mode.
 */
async function settleForHydration(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1200);
}

/**
 * Sign in via the credentials form on /sign-in. Fills the email/password
 * inputs, submits, and waits until the authenticated nav ("Sign out") renders.
 */
export async function signIn(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto("/sign-in");
  // Re-fill + retry the submit until we actually leave /sign-in (a pre-hydration
  // native submit reloads /sign-in as a GET and clears the fields). Settle for
  // hydration at the start of every attempt, since a native reload restarts the
  // hydration clock. Then assert the authenticated header separately (the
  // callback nav can be a cold Next compile on first hit).
  //
  // Guard: a previous attempt's submit may have succeeded with the navigation
  // landing AFTER its waitForURL gave up (cold next-dev compiles can exceed
  // it). In that case the retry runs on an already-signed-in page with no
  // email input, so skip straight to the URL check instead of re-filling.
  await expect(async () => {
    if (new URL(page.url()).pathname.startsWith("/sign-in")) {
      await settleForHydration(page);
      await page.locator('input[type="email"]').fill(email);
      await page.locator('input[type="password"]').fill(password);
      await page.getByRole("button", { name: "Sign in" }).click();
    }
    await page.waitForURL((url) => !url.pathname.startsWith("/sign-in"), {
      timeout: 15000,
    });
  }).toPass({ timeout: 60000 });
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 20000,
  });
}

/**
 * Register a new account via /sign-up. The first form input is Full name,
 * followed by email and password. On success the app hard-navigates to /intake.
 * Returns without asserting success so callers can inspect error copy.
 */
export async function register(
  page: Page,
  name: string,
  email: string,
  password: string,
): Promise<void> {
  await page.goto("/sign-up");
  await settleForHydration(page);
  // Guard against the same pre-hydration native-submit race as signIn: if the
  // click lands before React attaches, /sign-up reloads and clears the fields.
  // Retry (re-filling) until we either leave /sign-up (success -> /intake) or an
  // inline error/validation surfaces. A settled, hydrated submit resolves on the
  // first pass.
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.locator("#display_name").fill(name);
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    try {
      await Promise.race([
        page.waitForURL((url) => !url.pathname.startsWith("/sign-up"), {
          timeout: 6000,
        }),
        page
          .locator('[role="alert"], p.text-status-danger-fg')
          .first()
          .waitFor({ state: "visible", timeout: 6000 }),
      ]);
      return;
    } catch {
      // Pre-hydration reload cleared the form (email now empty) -> retry.
      const emailVal = await page.locator('input[type="email"]').inputValue();
      if (emailVal !== "") return; // submit landed; caller will assert outcome
    }
  }
}

/** Sign out via the header control and wait for the logged-out nav. */
export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible({
    timeout: 15000,
  });
}
