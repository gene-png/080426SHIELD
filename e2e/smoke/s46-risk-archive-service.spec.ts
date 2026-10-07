import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * #896: archive a service from the Risk Register's duplicate banner, through
 * the SCREEN -- D-076's "works today" evidence for the control the banner
 * offers.
 *
 * Since #876, two engaged services of one kind and framework make Generate
 * refuse. The banner now names each of them with an archive button and a
 * confirm dialog (advisor, #736 6042801745). This spec seeds the duplicate on
 * a THROWAWAY tenant (the s30 pattern), archives one through the dialog, and
 * asserts the refusal clears and Generate is offered.
 *
 * Strings are copied from the advisor's approval, not from the component.
 */

const DUPLICATE_LEAD = "Archive the one this register should not draw on:";
const DIALOG_BODY = (title: string) =>
  `The Risk Register will stop drawing on ${title}: the next version you generate leaves out its findings, and publishing no longer waits for it. Nothing else changes: its assessments, its deliverables and the client's view of it stay as they are. Archiving cannot be undone.`;

async function setActiveClient(page: Page, clientId: string): Promise<void> {
  const res = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  expect(res.ok()).toBeTruthy();
}

async function openService(
  page: Page,
  prefix: "attack" | "zt",
  kind: string,
  title: string,
): Promise<string> {
  const svc = await page.request.post(`/api/proxy/${prefix}/services`, {
    data: { kind, title },
  });
  expect(svc.ok(), await svc.text()).toBeTruthy();
  const id = ((await svc.json()) as { id: string }).id;
  const a = await page.request.post(
    `/api/proxy/${prefix}/services/${id}/assessments`,
  );
  expect(a.ok(), await a.text()).toBeTruthy();
  return id;
}

test("archiving one of two same-kind services from the duplicate banner clears the refusal", async ({
  page,
}) => {
  test.slow();
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  const createdClient = await page.request.post("/api/proxy/admin/clients", {
    data: { legal_name: `QA Risk Archive ${Date.now()}` },
  });
  expect(createdClient.ok()).toBeTruthy();
  const clientId = ((await createdClient.json()) as { id: string }).id;
  await setActiveClient(page, clientId);

  await openService(page, "attack", "attack_coverage", "QA Archive ATT&CK");
  const keep = await openService(
    page,
    "zt",
    "zero_trust_cisa",
    "QA Archive ZT One",
  );
  const drop = await openService(
    page,
    "zt",
    "zero_trust_cisa",
    "QA Archive ZT Two",
  );

  await page.goto("/admin/risk-register");
  await expect(
    page.getByRole("heading", { name: "Risk Register", exact: true }),
  ).toBeVisible({ timeout: 60000 });

  // The refusal and its remedy, before anything is archived.
  await expect(
    page.getByTestId("risk-register-duplicate-inputs"),
  ).toBeVisible();
  const archive = page.getByTestId("risk-register-duplicate-archive");
  await expect(archive).toContainText(DUPLICATE_LEAD);
  await expect(
    archive.getByRole("button", { name: "Archive QA Archive ZT One" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate" })).toBeDisabled();

  // Cancel archives nothing.
  await archive
    .getByRole("button", { name: "Archive QA Archive ZT Two" })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Archive QA Archive ZT Two?",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(DIALOG_BODY("QA Archive ZT Two"));
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(
    page.getByTestId("risk-register-duplicate-inputs"),
  ).toBeVisible();

  // Confirm archives exactly that service.
  await archive
    .getByRole("button", { name: "Archive QA Archive ZT Two" })
    .click();
  await expect(dialog).toBeVisible();
  const deleted = page.waitForResponse(
    (r) =>
      r.request().method() === "DELETE" &&
      r.url().endsWith(`/api/proxy/admin/services/${drop}`),
  );
  await dialog.getByRole("button", { name: "Yes, archive" }).click();
  expect((await deleted).status()).toBe(204);

  // Positive state first (Generate offered), then the absences.
  await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled({
    timeout: 30000,
  });
  await expect(page.getByTestId("risk-register-duplicate-inputs")).toHaveCount(
    0,
  );
  await expect(page.getByTestId("risk-register-duplicate-archive")).toHaveCount(
    0,
  );

  const dropped = await page.request.get(`/api/proxy/admin/services/${drop}`);
  expect(((await dropped.json()) as { status: string }).status).toBe(
    "archived",
  );
  const kept = await page.request.get(`/api/proxy/admin/services/${keep}`);
  expect(((await kept.json()) as { status: string }).status).not.toBe(
    "archived",
  );
});
