import { expect, type Page } from "@playwright/test";

/**
 * Open one section of a service in the client frame (#1376). The old
 * `/admin/services/{id}/{kind}` URL lands on Overview, and Tech Debt now shows
 * each block in its own section, so a spec that uploads or edits the table
 * opens that section through the section bar, as a reader does. The section
 * bar is the contract: its link names are Gene's tab names.
 */
export async function openSection(page: Page, label: string): Promise<void> {
  const bar = page.getByRole("navigation", { name: "Service sections" });
  await expect(bar).toBeVisible({ timeout: 30000 });
  await bar.getByRole("link", { name: label, exact: true }).click();
  await expect(
    bar.getByRole("link", { name: label, exact: true }),
  ).toHaveAttribute("aria-current", "page", { timeout: 30000 });
}
