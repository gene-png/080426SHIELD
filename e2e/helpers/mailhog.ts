import { type APIRequestContext } from "@playwright/test";

/**
 * Shared MailHog reader for the e2e suite. Extracted from
 * s21-email-verify.spec.ts (Sprint 8 T0) so the release-notify (T2),
 * verify/forgot/reset pages (T3), and any future mail-asserting specs read the
 * inbox the same way.
 *
 * MailHog is wired at :1025 (SMTP) / :8025 (HTTP API + UI); email delivery is on
 * by default in dev/CI compose since Sprint 7 T3.
 */

/** MailHog HTTP API v2 base. */
export const MAILHOG_API = "http://localhost:8025/api/v2";

export interface MailHogItem {
  Content: { Headers: Record<string, string[]>; Body: string };
}

/** The Subject header of a MailHog message ("" if absent). */
export function subjectOf(item: MailHogItem): string {
  return item.Content.Headers["Subject"]?.[0] ?? "";
}

/**
 * Poll MailHog for the most recent message to `email`; null if none arrives
 * before the timeout.
 *
 * Pass `subject` to require the Subject header to contain it (case-insensitive):
 * registration also emails the recipient, so "latest for recipient" can select
 * the wrong message (a first-message-wins race). Subject-matching picks the
 * intended mail regardless of ordering. Omit it to keep the original
 * latest-for-recipient behavior.
 */
export async function fetchLatestMessage(
  request: APIRequestContext,
  email: string,
  options: { subject?: string; timeoutMs?: number } = {},
): Promise<MailHogItem | null> {
  const { subject, timeoutMs = 8000 } = options;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request
      .get(`${MAILHOG_API}/search?kind=to&query=${encodeURIComponent(email)}`)
      .catch(() => null);
    if (res?.ok()) {
      const body = (await res.json()) as { items?: MailHogItem[] };
      const items = body.items ?? [];
      const match = subject
        ? items.find((item) =>
            subjectOf(item).toLowerCase().includes(subject.toLowerCase()),
          )
        : items[0];
      if (match) {
        return match;
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

/** MailHog quoted-prints long links across lines; join then pull the token. */
export function extractToken(body: string): string | null {
  const collapsed = body.replace(/=\r?\n/g, "").replace(/=3D/g, "=");
  const match = collapsed.match(/token=([A-Za-z0-9_-]+)/);
  return match ? match[1] : null;
}
