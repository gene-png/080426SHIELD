import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

/**
 * #643 / #685 round 1: the step-2 table's Name column must be READABLE at
 * laptop widths.
 *
 * The first fix removed the sideways scroll by sizing four columns inside a
 * 60rem `table-fixed` minimum, which left Name about 5.6rem: five characters,
 * so two different products both read "Crowd". That was found by arithmetic,
 * and nobody had rendered it. This spec renders it. It measures every Name input
 * against a 24-character string drawn in that input's OWN computed font, so the
 * threshold is a property of the page, not a guessed pixel count.
 *
 * The seeded Atlas Tech Debt service holds a RELEASED list, so the table renders
 * read-only with real rows and nothing is written.
 */

const VIEWPORTS = [
  { name: "laptop-1280", width: 1280, height: 800 },
  { name: "laptop-1440", width: 1440, height: 900 },
];

/** Twenty-four characters, a realistic product-name length. */
const SAMPLE = "Endpoint Detection Suite";

for (const vp of VIEWPORTS) {
  test(`step-2 Name column fits a ${SAMPLE.length}-character name at ${vp.name}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    const serviceId = await atlasServiceId(page, "tech_debt");
    await page.goto(`/admin/services/${serviceId}/tech-debt`);

    const names = page.getByRole("textbox", { name: "Name", exact: true });
    await expect(names.first()).toBeVisible({ timeout: 30_000 });

    const measured = await names.evaluateAll((els, sample) => {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("no 2d canvas context to measure text with");
      return els.map((el) => {
        const cs = getComputedStyle(el);
        ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        const content =
          el.clientWidth -
          parseFloat(cs.paddingLeft) -
          parseFloat(cs.paddingRight);
        return {
          content: Math.round(content),
          needed: Math.ceil(ctx.measureText(sample).width),
        };
      });
    }, SAMPLE);

    // Not vacuous: the seeded list has rows.
    expect(measured.length).toBeGreaterThan(0);
    const narrowest = Math.min(...measured.map((m) => m.content));
    const needed = measured[0].needed;
    // Printed so the CI log carries the numbers the PR body quotes.
    console.log(
      `[s44] ${vp.name}: ${measured.length} Name inputs; narrowest content width ${narrowest}px; "${SAMPLE}" needs ${needed}px`,
    );
    test.info().annotations.push({
      type: "measured",
      description: `${vp.name}: narrowest ${narrowest}px, needs ${needed}px`,
    });
    expect(
      narrowest,
      `a Name input at ${vp.name} is ${narrowest}px wide inside its padding; "${SAMPLE}" needs ${needed}px`,
    ).toBeGreaterThanOrEqual(needed);
  });
}
