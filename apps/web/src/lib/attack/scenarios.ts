"use client";

import type { AiRunStarted, AiServes } from "@/lib/aiRuns/types";

/** The ATT&CK what-if (#802 slice A). Mirrors `app/schemas/attack_scenario.py`. */

export interface ScenarioRollup {
  coverage_pct: number;
  covered: number;
  partial: number;
  gap: number;
  not_applicable: number;
  /** Withheld from the percentage; rendered beside it (#102). */
  pending_review: number;
  scored_count: number;
  catalogue_count: number;
  /** #621's outside counts; null for a base approved before #620's rules. */
  unable_to_determine: number | null;
  outside_control_surface: number | null;
}

export interface ScenarioDifference {
  technique_code: string;
  today: string | null;
  after: string | null;
  scored_higher: boolean;
}

export interface ScenarioTechnique {
  technique_code: string;
  detection_tools: string[];
  prevention_tools: string[];
  response_tools: string[];
}

export interface Scenario {
  id: string;
  service_id: string;
  state: "draft" | "confirmed" | "discarded";
  removed: string[];
  affected_codes: string[];
  base_assessment_id: string;
  base_version: number;
  base_approved_at: string | null;
  stale: boolean;
  analysis_available: boolean;
  ai_run_id: string | null;
  run_status: "running" | "completed" | "failed" | null;
  /** Why the run failed, as the run records it; null unless `failed`. */
  run_error: { reason: string | null; message: string | null } | null;
  today: ScenarioRollup;
  after: ScenarioRollup | null;
  differences: ScenarioDifference[];
  techniques: ScenarioTechnique[];
  dropped: Record<string, number> | null;
  not_reassessed: string[] | null;
  scored_higher: number | null;
}

export interface ScenarioBase {
  assessment_id: string;
  version: number;
  approved_at: string | null;
  tools: string[];
}

export interface ScenarioSummary {
  id: string;
  state: Scenario["state"];
  removed: string[];
  affected_count: number;
  base_version: number;
  created_at: string;
}

export interface ScenarioList {
  base: ScenarioBase | null;
  scenarios: ScenarioSummary[];
}

/**
 * Its own error class rather than `client.ts`'s: the workspace's tests mock
 * that module whole, and the panel must not depend on what a mock exports.
 * Same shape (`status`, `payload`), so `clientFacingError` reads it.
 */
export class ScenarioProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`ATT&CK what-if proxy ${status}`);
  }
}

async function request<T>(
  url: string,
  init: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  const { method = "GET", body } = init;
  const res = await fetch(url, {
    method,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  // Read the body ONCE (CLAUDE.md, the fetch-body entry).
  const raw = await res.text();
  let payload: unknown;
  try {
    payload = raw ? JSON.parse(raw) : undefined;
  } catch {
    payload = raw;
  }
  if (!res.ok) throw new ScenarioProxyError(res.status, payload);
  return payload as T;
}

export function fetchScenarios(serviceId: string): Promise<ScenarioList> {
  return request(`/api/proxy/attack/services/${serviceId}/scenarios`);
}

export function createScenario(
  serviceId: string,
  removed: string[],
): Promise<Scenario> {
  return request(`/api/proxy/attack/services/${serviceId}/scenarios`, {
    method: "POST",
    body: { removed },
  });
}

export function fetchScenario(scenarioId: string): Promise<Scenario> {
  return request(`/api/proxy/attack/scenarios/${scenarioId}`);
}

export function runScenario(
  scenarioId: string,
  serves: AiServes,
): Promise<AiRunStarted> {
  return request(`/api/proxy/attack/scenarios/${scenarioId}/run`, {
    method: "POST",
    body: { serves },
  });
}

export function discardScenario(scenarioId: string): Promise<Scenario> {
  return request(`/api/proxy/attack/scenarios/${scenarioId}/discard`, {
    method: "POST",
  });
}
