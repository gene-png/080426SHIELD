import { permanentRedirect } from "next/navigation";

import type { JSX } from "react";

/**
 * `/documents` moved to `/results` (UX finding 18).
 *
 * Reports were downloaded from Documents while dashboards were reached from
 * Home or a "View dashboard" link, so a client had three places to look for the
 * outcome of one engagement and no way to know which held what. `/results` is
 * now the single place: one card per service carrying the dashboard, the PDF,
 * the spreadsheet, the version, the release date and the status.
 *
 * This redirect is PERMANENT and stays. The old path is in released
 * notification emails already sitting in people's inboxes, and those have to
 * keep working — a 404 on a link we sent is worse than an extra route.
 */
export default function DocumentsRedirect(): JSX.Element {
  permanentRedirect("/results");
}
