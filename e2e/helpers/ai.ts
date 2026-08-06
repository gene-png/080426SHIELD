import type { Page } from "@playwright/test";

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
  const dialog = page.getByRole("alertdialog", { name: "No API key loaded" });
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
