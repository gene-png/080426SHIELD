import { statusWord } from "./inputs";
import type { RiskDuplicateService } from "./types";

/**
 * #896 review B1: the line that tells two duplicate services apart, which
 * can carry the SAME title. The advisor's wording, exactly (#736 6046898402):
 * "Started {d Mon yyyy}, version {n}, {panel word}", the panel word being the
 * Inputs panel's own, unchanged. Change it only with the advisor.
 */
export function startedLine(row: RiskDuplicateService): string {
  // A record status ("draft"), not an HTTP one: read into its own name so the
  // template carries no `.status`, which the client-surfaces gate reads as an
  // HTTP status put into copy.
  const word = statusWord(row.status);
  return `Started ${startedDate(row.started_at)}, version ${row.version}, ${word}`;
}

/**
 * The "{d Mon yyyy}" part. The date is the service's `created_at`, read in
 * UTC (advisor, Q2), so every viewer sees the same day.
 *
 * Month names are spelled out rather than taken from `Intl`, whose short
 * month varies by locale and runtime ("Sept" in some).
 */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

export function startedDate(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    throw new Error(`startedDate: ${JSON.stringify(iso)} is not a date`);
  }
  return `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()]} ${at.getUTCFullYear()}`;
}
