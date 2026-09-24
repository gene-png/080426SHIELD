/**
 * Date-only rendering.
 *
 * Deadlines, release dates and similar fields are CALENDAR dates: the client
 * picked "30 June 2027", not an instant. The API serialises them as UTC
 * midnight, so `new Date(value).toLocaleDateString()` moves them back a day for
 * every viewer west of UTC — a deadline entered as 2027-06-30 rendered as
 * 6/29/2027 in the 2026-08-04 review. Parse the calendar parts and build the
 * date in LOCAL time so the day is preserved wherever it is read.
 */

const DATE_PARTS = /^(\d{4})-(\d{2})-(\d{2})/;

/** Format a date-only value for display, or null when there isn't one. */
export function formatDateOnly(
  value: string | null | undefined,
  locales?: Intl.LocalesArgument,
): string | null {
  const parsed = parseDateOnly(value);
  return parsed ? parsed.toLocaleDateString(locales) : null;
}

/** The calendar date as a local-midnight Date, or null when unparseable. */
export function parseDateOnly(value: string | null | undefined): Date | null {
  if (!value) return null;
  const m = DATE_PARTS.exec(value.trim());
  if (!m) return null;
  const [, y, mo, d] = m;
  const date = new Date(Number(y), Number(mo) - 1, Number(d));
  return Number.isNaN(date.getTime()) ? null : date;
}

// An INSTANT -- released, finalized, submitted -- in UTC, with the zone named.
// Every surface that shows one of these goes through here, so the admin card
// and the admin table cannot show one release as two days (the dashboards'
// badge is pinned to UTC too). Unlike `formatDateOnly`, which is right to use
// the viewer's zone for a calendar date.
const INSTANT_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

/** Format an instant in UTC, naming the zone; "—" for none, the raw text if unparseable. */
export function formatInstantUtc(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : INSTANT_FMT.format(d);
}
