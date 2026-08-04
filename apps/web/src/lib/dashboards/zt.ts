/**
 * Client Zero Trust maturity dashboard — types + pure transforms (D-035).
 * Mirrors the backend `ZtDashboardResponse` (apps/api/app/schemas/clients.py).
 */

export interface ZtPillar {
  code: string;
  name: string;
  capability_count: number;
  answered_count: number;
  current_pct: number | null;
  current_label: string;
  target_pct: number | null;
  target_label: string;
  gap_pct: number;
  weakest: string[];
}

export interface ZtDashboardData {
  service_id: string;
  service_title: string;
  released_at: string;
  deliverable_version: number;
  framework: string;
  framework_label: string;
  current_label: string;
  current_pct: number | null;
  target_label: string;
  target_pct: number | null;
  largest_gap_pillar: string | null;
  largest_gap_pct: number;
  pillars: ZtPillar[];
}

export interface RadarData {
  labels: string[];
  current: number[];
  target: number[];
}

/** Current-vs-target maturity % per pillar for the radar chart. */
export function radarData(pillars: ZtPillar[]): RadarData {
  return {
    labels: pillars.map((p) => p.name),
    current: pillars.map((p) => p.current_pct ?? 0),
    target: pillars.map((p) => p.target_pct ?? 0),
  };
}

/** Pillars ordered by the largest current→target gap first (focus ordering). */
export function pillarsByGap(pillars: ZtPillar[]): ZtPillar[] {
  return [...pillars].sort((a, b) => b.gap_pct - a.gap_pct);
}
