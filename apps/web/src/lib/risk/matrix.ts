/**
 * Risk 5x5 tier helpers — a faithful client-side mirror of the Python
 * app/risk/engine.py so the dashboard heatmap colours each cell the same way
 * the backend tiers an entry. The backend remains the source of truth; this is
 * presentation only.
 */

export const LIKELIHOODS = [
  "very_low",
  "low",
  "medium",
  "high",
  "very_high",
] as const;
export const IMPACTS = [
  "negligible",
  "minor",
  "moderate",
  "major",
  "catastrophic",
] as const;

export type Likelihood = (typeof LIKELIHOODS)[number];
export type Impact = (typeof IMPACTS)[number];
export type RiskTier = "critical" | "high" | "medium" | "low" | "negligible";

export function riskScore(l: Likelihood, i: Impact): number {
  return (LIKELIHOODS.indexOf(l) + 1) * (IMPACTS.indexOf(i) + 1);
}

export function tierFor(l: Likelihood, i: Impact): RiskTier {
  const ii = IMPACTS.indexOf(i);
  if ((l === "high" || l === "very_high") && i === "catastrophic")
    return "critical";
  if (l === "very_high" && ii >= IMPACTS.indexOf("major")) return "critical";
  const s = riskScore(l, i);
  if (s >= 15) return "high";
  if (s >= 9) return "medium";
  if (s >= 4) return "low";
  return "negligible";
}

export const TIER_COLOR: Record<RiskTier, { bg: string; fg: string }> = {
  critical: { bg: "#fee2e2", fg: "#991b1b" },
  high: { bg: "#ffedd5", fg: "#9a3412" },
  medium: { bg: "#fef9c3", fg: "#854d0e" },
  low: { bg: "#dcfce7", fg: "#166534" },
  negligible: { bg: "#f1f5f9", fg: "#475569" },
};

export function titleCase(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function isLikelihood(s: string | null): s is Likelihood {
  return s != null && (LIKELIHOODS as readonly string[]).includes(s);
}

export function isImpact(s: string | null): s is Impact {
  return s != null && (IMPACTS as readonly string[]).includes(s);
}
