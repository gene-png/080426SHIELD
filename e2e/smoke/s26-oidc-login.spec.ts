import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD } from "../helpers/auth";

/**
 * SMOKE_TEST OIDC section (Sprint 9 T7, D-032): the hybrid Keycloak SSO seam,
 * end to end through a real browser.
 *
 * OPT-IN, and doubly gated. The seam is dormant on the default stack
 * (`SHIELD_AUTH_OIDC_ENABLED` defaults false), so with the flag off the
 * "Sign in with Keycloak" button does not render and the "keycloak" provider
 * does not exist. This spec self-skips unless `E2E_OIDC=1`, so the default
 * suite runs ZERO tests from this file and its pass/fail count is unchanged.
 *
 * To run it you must FIRST flip the seam on and rebuild the stack:
 *
 *   1. Add `SHIELD_AUTH_OIDC_ENABLED=true` to the repo-root `.env`.
 *   2. `docker compose up -d --force-recreate api web`
 *      (web reads the flag at provider registration, api at boot readiness).
 *   3. If the realm export (`infra/keycloak/shield-realm.json`) changed since it
 *      was last imported, wipe the keycloak volume so the new realm re-imports:
 *      `docker compose stop keycloak`
 *      `docker volume rm shield-v2_keycloak-data`
 *      `docker compose up -d keycloak`
 *   4. `E2E_OIDC=1 npx playwright test smoke/s26-oidc-login.spec.ts`
 *
 * ALWAYS restore afterward — remove the flag line and
 * `docker compose up -d --force-recreate api web`, then re-run the default
 * suite to confirm the credentials path still signs in. The flag must NEVER be
 * committed on.
 *
 * The two paths this proves:
 *  - POSITIVE: `admin@kentro.example` (in Keycloak AND in the SHIELD DB) makes a
 *    full round trip through the real Keycloak login form and lands
 *    authenticated, and an admin API-backed page renders — proving the SHIELD
 *    bearer token minted by `POST /auth/oidc/exchange` works end to end.
 *  - NEGATIVE: `nolocal@atlas.example` (in Keycloak, but NOT in the SHIELD DB)
 *    authenticates against Keycloak, the backend exchange refuses it
 *    (`oidc_no_local_account`), and the SessionExpiryGuard signs the half-auth
 *    session out to `/sign-in?reason=oidc_exchange_failed` with a loud banner.
 *
 * Keycloak's login page is NOT our UI, so it is driven by Keycloak's stable ids
 * (`#username` / `#password` / `#kc-login`), never by our design-system copy.
 */

test.skip(
  process.env.E2E_OIDC !== "1",
  "OIDC hybrid SSO e2e — opt-in; set E2E_OIDC=1 after flipping SHIELD_AUTH_OIDC_ENABLED=true and recreating api+web (see the file header).",
);

const NOLOCAL_EMAIL = "nolocal@atlas.example";
// Both the seeded Keycloak users share the demo password (infra/keycloak realm
// export, T5). The admin identity reuses the shared credentials constant.
const KEYCLOAK_PASSWORD = ADMIN_PASSWORD;

/**
 * Kick off the Keycloak redirect from /sign-in and wait for Keycloak's own
 * login form to render. Wrapped in a retry because the first hit is a cold
 * next-dev compile and the click must land after React hydration (a
 * pre-hydration click on the button's onClick is a no-op, same race the
 * credentials helper guards).
 */
async function startKeycloakSignIn(page: Page): Promise<void> {
  await expect(async () => {
    await page.goto("/sign-in");
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.waitForTimeout(1000);
    // "Sign in with Keycloak" is unambiguous — getByRole name matching is
    // substring, but the credentials submit button's name is just "Sign in",
    // which does not contain this longer string, so the two never collide.
    await page.getByRole("button", { name: "Sign in with Keycloak" }).click();
    // Keycloak serves its login form on localhost:8080.
    await page.waitForSelector("#username", { timeout: 15000 });
  }).toPass({ timeout: 60000 });
}

/** Fill and submit Keycloak's stock login form (its stable ids, not our UI). */
async function submitKeycloakForm(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.fill("#username", email);
  await page.fill("#password", password);
  await page.click("#kc-login");
}

test.describe("s26 hybrid Keycloak OIDC sign-in (opt-in, E2E_OIDC=1)", () => {
  test("positive: admin round-trips through Keycloak and an API-backed page renders", async ({
    page,
  }) => {
    test.slow();
    await startKeycloakSignIn(page);
    await submitKeycloakForm(page, ADMIN_EMAIL, KEYCLOAK_PASSWORD);

    // Back on the app, authenticated: the header exposes Sign out and the OIDC
    // failure banner is NOT showing (a successful exchange, not a rejection).
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
      timeout: 30000,
    });

    // End-to-end backend-token proof: the admin management list is gated behind
    // the SHIELD bearer token that /auth/oidc/exchange minted from the Keycloak
    // access token. If that token were missing or invalid the GET would 401 and
    // no client cards would render; a visible listitem means the exchanged
    // SHIELD token authenticated a real API call.
    await page.goto("/admin/management");
    await expect(
      page.getByRole("heading", { name: "Management", exact: true }),
    ).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("listitem").first()).toBeVisible({
      timeout: 30000,
    });
  });

  test("negative: a Keycloak identity with no local account lands on the loud banner", async ({
    page,
  }) => {
    test.slow();
    await startKeycloakSignIn(page);
    await submitKeycloakForm(page, NOLOCAL_EMAIL, KEYCLOAK_PASSWORD);

    // Keycloak authenticates the user (it exists there), but the backend
    // exchange refuses it with oidc_no_local_account. The jwt callback stamps
    // token.error = OIDC_EXCHANGE_ERROR and SessionExpiryGuard signs the dead
    // session out to /sign-in?reason=oidc_exchange_failed.
    await page.waitForURL(/\/sign-in\?.*reason=oidc_exchange_failed/, {
      timeout: 45000,
    });
    await expect(page.getByRole("alert")).toContainText(
      "no matching SHIELD account is active",
      { timeout: 20000 },
    );
  });
});
