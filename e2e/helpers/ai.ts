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
 * What one Tech Debt upload can lead to, watched from BEFORE it happens.
 *
 * Call it before `setInputFiles`, like any `waitForResponse`. Both waiters are
 * registered here on purpose: the page can start an extraction the moment the
 * upload responds, and a request waiter registered after reading that
 * response -- even one `await` later -- can miss it, then click the button
 * too (a second extraction) or throw that nothing started.
 */
export interface UploadWatch {
  upload: Promise<Response>;
  extractSent: Promise<"extracting" | "neither">;
}

export function watchUpload(page: Page): UploadWatch {
  const upload = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      /\/api\/proxy\/artifacts\/?$/.test(new URL(r.url()).pathname),
    { timeout: 120000 },
  );
  const extractSent = page
    .waitForRequest(
      (r) =>
        r.url().includes("/capability-lists/extract") && r.method() === "POST",
      { timeout: 120000 },
    )
    .then(
      () => "extracting" as const,
      () => "neither" as const,
    );
  return { upload, extractSent };
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
 * It targets THE UPLOADED FILE's row, by the artifact id in its Download link.
 * The documents panel lists every document for the CLIENT, so "a button" --
 * or "one more button than before", which cannot tell a panel still loading
 * from a loaded one -- can extract an older upload into this spec's service.
 *
 * It waits for whichever comes first: an extraction request seen since
 * `watchUpload` (the page started one itself), or that row's button. It fails
 * LOUDLY, naming the cause, when neither happens within 60 s of the upload
 * responding, rather than leaving the caller to time out on a response and
 * blame the API.
 */
export async function extractAfterUpload(
  page: Page,
  extractDone: Promise<Response>,
  watch: UploadWatch,
): Promise<Response> {
  const upload = await watch.upload;
  if (!upload.ok()) {
    throw new Error(`the upload itself failed: HTTP ${upload.status()}`);
  }
  const { id } = (await upload.json()) as { id: string };
  const row = page.locator("li").filter({
    has: page.locator(`a[href="/api/proxy/artifacts/${id}/download"]`),
  });
  const button = row.getByRole("button", { name: "Extract from this" });
  const first = await Promise.race([
    watch.extractSent,
    button.waitFor({ state: "visible", timeout: 60000 }).then(
      () => "button" as const,
      () => "neither" as const,
    ),
  ]);
  if (first === "neither") {
    throw new Error(
      `uploaded artifact ${id}: no extraction started and its row never ` +
        `offered "Extract from this" within 60 s -- check the documents panel ` +
        `for an error before suspecting the extraction API`,
    );
  }
  if (first === "button") {
    await button.click();
    await acknowledgeOfflineAi(page);
  }
  return extractDone;
}
