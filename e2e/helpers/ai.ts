import type { Page, Response } from "@playwright/test";

/**
 * Acknowledge the offline Run-AI guard if it appears.
 *
 * Since the 2026-08-05 remediation, every Run-AI entry point is wrapped in
 * `RunAiGuard`: with no provider key loaded the first click explains that the
 * output will be canned demo content and offers "Load a key" / "Continue
 * offline" instead of running. CI and the local stack both run fixture mode
 * with no key, so specs that press Run AI now meet that dialog.
 *
 * This is intentional product behaviour, not a test obstacle — a fixture run
 * silently overwriting a real client self-assessment is precisely what the
 * guard exists to stop. Specs acknowledge it explicitly, which also keeps the
 * dialog itself under test on every run.
 *
 * Safe to call unconditionally: it returns immediately when AI is live, when
 * the admin already acknowledged in this session, or when the control being
 * clicked is not guarded.
 *
 * The wait is deliberately generous. At 4s this helper gave up BEFORE the
 * dialog rendered on a next-dev cold compile under suite load, returned
 * silently, and left the guard open — so the caller's `waitForResponse` sat
 * there for its full two minutes and then failed with "timeout waiting for
 * event: response", which points at the API rather than at the un-clicked
 * button actually holding things up. Waiting longer costs nothing when the
 * dialog is genuinely absent (the common path is that it appears within
 * milliseconds); mis-reporting the cause cost an afternoon.
 */
const GUARD_TIMEOUT_MS = 20000;

export async function acknowledgeOfflineAi(page: Page): Promise<void> {
  const dialog = page.getByRole("alertdialog", {
    name: "AI is not ready to run live",
  });
  try {
    await dialog.waitFor({ state: "visible", timeout: GUARD_TIMEOUT_MS });
  } catch {
    return; // No guard shown — nothing to acknowledge.
  }
  await dialog.getByRole("button", { name: "Continue offline" }).click();
  // The dialog must actually close: a click that lands while React is still
  // attaching is a no-op, and the caller would otherwise wait on a request
  // that never gets sent.
  await dialog.waitFor({ state: "hidden", timeout: GUARD_TIMEOUT_MS });
}

/**
 * How many "Extract from this" buttons the documents panel shows, once that
 * number has held steady for a second. Read while the panel is still loading,
 * a service's EXISTING documents would arrive later and look like the upload.
 */
export async function countExtractButtons(page: Page): Promise<number> {
  const buttons = page.getByRole("button", { name: "Extract from this" });
  let last = await buttons.count();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(1000);
    const now = await buttons.count();
    if (now === last) return now;
    last = now;
  }
  return last;
}

/**
 * After a Tech Debt upload, get the extraction to run, whichever way the page
 * offers it.
 *
 * With AI live (or offline and already acknowledged) the upload starts the
 * extraction itself. Offline and unacknowledged, it only lists the file, and
 * the guarded "Extract from this" button is the way in. Since #472/#509 the
 * page decides only once the AI status has SETTLED, so the button can appear
 * a moment after the upload. The specs this replaces checked `isVisible()`
 * once, immediately: they passed only because the upload used to beat the
 * status request and auto-extract on a null status, which was #509's bug.
 *
 * `buttonsBefore` is `countExtractButtons` taken just before the upload. The
 * panel lists documents newest first, but a service that already holds
 * documents shows their buttons at once, so waiting for "a button" would
 * extract an OLD file. This waits for one MORE button than before -- the new
 * upload's -- and clicks the first, which is the newest.
 *
 * It waits for whichever comes first: the extraction response, or that new
 * button. If it is the button, it clicks and acknowledges offline mode.
 */
export async function extractAfterUpload(
  page: Page,
  extractDone: Promise<Response>,
  buttonsBefore: number,
): Promise<Response> {
  const buttons = page.getByRole("button", { name: "Extract from this" });
  const newButtonListed = (async () => {
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      if ((await buttons.count()) > buttonsBefore) return "button" as const;
      await page.waitForTimeout(250);
    }
    return "neither" as const;
  })();
  const first = await Promise.race([
    extractDone.then(() => "extracted" as const),
    newButtonListed,
  ]);
  if (first === "button") {
    await buttons.first().click();
    await acknowledgeOfflineAi(page);
  }
  return extractDone;
}
