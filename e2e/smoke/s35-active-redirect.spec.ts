import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * Issue 6: /admin/active was a stub page whose entire body was a paragraph and
 * a "Go to the intake queue" button — a link that led nowhere new, breaking the
 * Navigation_Spec §12 rule that no control may dead-end.
 *
 * The nav entry now points straight at the queue, and the route survives only
 * as a redirect so existing bookmarks and deep links still land somewhere
 * useful rather than 404ing.
 *
 * This spec pins both halves of that contract:
 *   1. Navigating to /admin/active lands on /admin/queue.
 *   2. The admin sidebar no longer offers an "Active Work" destination.
 */

test("admin: /admin/active redirects to the intake queue and the nav entry is gone", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  await page.goto("/admin/active");

  // The redirect resolves to the queue — not a 404, and not the old stub.
  await expect
    .poll(() => new URL(page.url()).pathname, {
      message: "/admin/active must redirect to /admin/queue",
    })
    .toBe("/admin/queue");

  // The old stub's giveaway copy must be gone.
  await expect(
    page.getByRole("link", { name: "Go to the intake queue" }),
  ).toHaveCount(0);

  // And the sidebar no longer advertises a separate Active Work destination.
  const nav = page.getByRole("navigation", { name: "Primary" }).first();
  await expect(nav.getByRole("link", { name: "Active Work" })).toHaveCount(0);
  await expect(
    nav.getByRole("link", { name: "Intake Queue", exact: true }).first(),
  ).toBeVisible();
});
