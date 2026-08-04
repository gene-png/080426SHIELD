import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * SMOKE_TEST.md section 15 (security headers). The response for every path is
 * hardened in apps/web/next.config.mjs via async headers() applied to
 * "/:path*". This spec pins the six headers the smoke checklist calls out and
 * confirms the signed-in dashboard renders with no CSP-blocked resources.
 *
 * All six headers ARE implemented (CSP, X-Frame-Options, X-Content-Type-Options,
 * Referrer-Policy, Strict-Transport-Security, Permissions-Policy); none are
 * backlog. If a future edit drops one, the corresponding assertion fails loudly.
 */

test("home response carries the full security-header set", async ({ page }) => {
  const response = await page.goto("/");
  expect(response, "no response for /").not.toBeNull();
  const headers = response!.headers();

  // Content-Security-Policy: self-only, framing denied, no remote origins.
  const csp = headers["content-security-policy"];
  expect(csp, "Content-Security-Policy missing").toBeTruthy();
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("object-src 'none'");

  // Clickjacking + MIME-sniffing defenses.
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");

  // Referrer policy is present (strict-origin-when-cross-origin in config).
  expect(headers["referrer-policy"], "Referrer-Policy missing").toBeTruthy();
  expect(headers["referrer-policy"]).toContain("strict-origin");

  // HSTS: long max-age with subdomains + preload.
  const hsts = headers["strict-transport-security"];
  expect(hsts, "Strict-Transport-Security missing").toBeTruthy();
  expect(hsts).toContain("max-age=");
  expect(hsts).toContain("includeSubDomains");

  // Permissions-Policy locks down powerful features.
  const pp = headers["permissions-policy"];
  expect(pp, "Permissions-Policy missing").toBeTruthy();
  expect(pp).toContain("camera=()");

  // Defense in depth: the Powered-By banner is suppressed.
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("signed-in dashboard has no CSP-blocked resources", async ({ page }) => {
  // Capture only CSP-violation console output; unrelated app warnings/errors are
  // out of scope for this header check.
  const cspErrors: string[] = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (
      msg.type() === "error" &&
      (/content security policy/i.test(text) ||
        /refused to (load|execute|connect|apply)/i.test(text) ||
        /violates the following content security policy/i.test(text))
    ) {
      cspErrors.push(text);
    }
  });

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Land on an authenticated admin surface so bundled scripts/styles load under
  // the strict CSP, then let the client bundle settle.
  await page.getByRole("link", { name: "Admin" }).click();
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1500);

  expect(
    cspErrors,
    `CSP-blocked resources on the signed-in dashboard: ${cspErrors.join(" | ")}`,
  ).toEqual([]);
});
