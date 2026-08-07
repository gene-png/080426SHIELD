import { expect, test } from "@playwright/test";

import { signIn } from "../helpers/auth";

/**
 * IA appendix: "Messages / Help — consultant messages, service explanations,
 * support and accessibility contact."
 *
 * Messages already had a home; the explanations and the contact routes did not,
 * so a client could see "MITRE ATT&CK Coverage Mapping" on their dashboard with
 * nowhere to find out what it is.
 *
 * The service copy comes from the same `SERVICE_DESCRIPTIONS` map the intake
 * picker reads, so this asserts the LABELS render rather than duplicating the
 * sentences here — a spec that restates the copy just makes the copy harder to
 * edit without proving anything extra.
 */

const CLIENT_EMAIL = "client@atlas.example";
const CLIENT_PASSWORD = "DemoPass!2026";

const SERVICE_HEADINGS = [
  "Technical Debt Review",
  "Zero Trust Assessment (CISA ZTMM 2.0)",
  "Zero Trust Assessment (DoD ZTRA)",
  "NIST CSF 2.0 Assessment",
  "MITRE ATT&CK Coverage Mapping",
];

test("help: every service is explained and the support routes resolve", async ({
  page,
}) => {
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto("/help");

  await expect(
    page.getByRole("heading", { name: "Help", level: 1 }),
  ).toBeVisible({ timeout: 30_000 });

  // Each service is named, and carries a non-empty explanation beneath it.
  for (const name of SERVICE_HEADINGS) {
    const card = page.locator("li", {
      has: page.getByRole("heading", { name, exact: true }),
    });
    await expect(card, `${name} must be explained on /help`).toHaveCount(1);
    const text = (await card.innerText()).replace(name, "").trim();
    expect(text.length, `${name} must carry a description`).toBeGreaterThan(20);
  }

  // The three support routes are present and are real destinations.
  for (const [label, path] of [
    ["Open messages →", "/messages"],
    ["Accessibility statement →", "/accessibility"],
    ["Account settings →", "/account"],
  ] as const) {
    await expect(page.getByRole("link", { name: label })).toHaveAttribute(
      "href",
      path,
    );
  }
});

test("help: reachable from the signed-in header, and the accessibility link works", async ({
  page,
}) => {
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto("/home");

  await page.getByRole("link", { name: "Help", exact: true }).first().click();
  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 30_000 })
    .toBe("/help");

  // Not a dead end: the accessibility route actually renders.
  await page.getByRole("link", { name: "Accessibility statement →" }).click();
  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 30_000 })
    .toBe("/accessibility");
});
