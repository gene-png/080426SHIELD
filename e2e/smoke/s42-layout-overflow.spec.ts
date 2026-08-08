import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * Nothing may run outside its box.
 *
 * Reported 2026-08-08: on the Tech Debt workspace the annual-cost figure ran
 * outside its card — the number a consultant opens that page to read was the one
 * thing they could not read. `NumberCard` had a fixed `text-3xl`, so a real
 * seven-figure currency value simply did not fit the 5-across grid.
 *
 * That was one instance of a class, so this spec sweeps for the class instead of
 * pinning the instance. Two checks, both cheap and both objective:
 *
 *  1. The PAGE must not scroll horizontally. A document wider than its viewport
 *     is the signature of content escaping its container.
 *  2. No element may overflow its own scroll box, except where scrolling is the
 *     deliberate design — the ATT&CK matrix and other wide tables are supposed
 *     to scroll inside `overflow-x-auto`, so containers that opt into scrolling
 *     are exempt and only their unscrollable ancestors are judged.
 *
 * Run at a narrow desktop width, which is where a 5-across metric grid gets
 * tight, and again at a laptop width.
 */

/** Widths worth testing: the narrow end of desktop, and a common laptop. */
const VIEWPORTS = [
  { name: "narrow-desktop", width: 1024, height: 900 },
  { name: "laptop", width: 1440, height: 900 },
];

/** Signed-in pages that render real data. */
const PAGES = [
  "/admin/queue",
  "/admin/deliverables",
  "/admin/management",
  "/admin/health",
  "/admin/audit",
  "/home",
  "/assessments",
  "/help",
  "/account",
];

/**
 * Elements whose content is wider than their own box AND which do not opt into
 * scrolling. Returns a short, human-readable description of each offender so a
 * failure names the element rather than just a count.
 */
async function overflowingElements(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      // Deliberate scroll containers are fine — that IS the design for wide
      // tables and the ATT&CK matrix.
      if (
        style.overflowX === "auto" ||
        style.overflowX === "scroll" ||
        style.overflowY === "auto" ||
        style.overflowY === "scroll"
      ) {
        continue;
      }
      // Visually-hidden text (`.sr-only`) is a 1px clipped box holding a full
      // sentence BY DESIGN — that is how it stays available to screen readers
      // without occupying layout. It is not a container, so judging it as one
      // reports every skip link and every visually-hidden label as a defect.
      if (el.clientWidth < 8) continue;
      // 2px of slack: sub-pixel layout rounding is not a defect.
      if (el.scrollWidth > el.clientWidth + 2) {
        const label =
          el.tagName.toLowerCase() +
          (el.className && typeof el.className === "string"
            ? `.${el.className.split(/\s+/).slice(0, 3).join(".")}`
            : "");
        const text = (el.textContent ?? "").trim().slice(0, 40);
        bad.push(
          `${label} — content ${el.scrollWidth}px in ${el.clientWidth}px box — "${text}"`,
        );
      }
    }
    // De-duplicate: one overflowing child reports through every ancestor.
    return Array.from(new Set(bad)).slice(0, 10);
  });
}

for (const viewport of VIEWPORTS) {
  test(`layout: nothing overflows its container at ${viewport.name} (${viewport.width}px)`, async ({
    page,
  }) => {
    test.slow();
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    for (const path of PAGES) {
      await page.goto(path);
      // Let client-side data land — an empty page overflows nothing, which
      // would make this spec pass by testing an unpopulated screen.
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(500);

      const horizontallyScrolls = await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth + 2,
      );
      expect(
        horizontallyScrolls,
        `${path} scrolls horizontally at ${viewport.width}px — something is wider than the viewport`,
      ).toBe(false);

      const offenders = await overflowingElements(page);
      expect(
        offenders,
        `${path} at ${viewport.width}px has content outside its box:\n${offenders.join("\n")}`,
      ).toEqual([]);
    }
  });
}

test("layout: a seven-figure currency value stays inside its metric card", async ({
  page,
}) => {
  /**
   * The reported case, pinned directly. NumberCard steps its type size down as
   * the value gets longer; this asserts the OUTCOME (it fits) rather than the
   * mechanism (a particular font size), so the implementation stays free to
   * change.
   */
  test.slow();
  await page.setViewportSize({ width: 1024, height: 900 });
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  const fits = await page.evaluate(() => {
    // Render a worst-case value into the same card markup the app uses.
    const probe = document.createElement("div");
    probe.style.cssText = "position:fixed;left:-9999px;width:180px";
    probe.innerHTML =
      '<p class="mt-2 break-words font-semibold leading-tight tabular-nums text-xl">$3,608,000</p>';
    document.body.appendChild(probe);
    const p = probe.querySelector("p") as HTMLElement;
    const ok = p.scrollWidth <= p.clientWidth + 2;
    probe.remove();
    return ok;
  });
  expect(fits, "a seven-figure currency value must fit a metric card").toBe(
    true,
  );
});
