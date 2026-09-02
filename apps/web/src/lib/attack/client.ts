"use client";

import type {
  AttackAiInputs,
  AttackAssessment,
  AttackCatalog,
  AttackCoveragePatch,
  AttackCoverageRow,
  AttackDeliverable,
  AttackHeatmap,
  AttackRunAiResponse,
} from "./types";

interface JsonRequestInit {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
}

async function jsonRequest<T>(
  url: string,
  init: JsonRequestInit = {},
): Promise<T> {
  const { body, method = "GET" } = init;
  const res = await fetch(url, {
    method,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    // Read the body ONCE, then try to parse it. Calling res.json() and then
    // res.text() on failure throws "body stream already read", which masked a
    // real 404 behind a confusing error while this path was unwired (issue 4).
    const raw = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
    throw new AttackProxyError(res.status, payload);
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
}

export class AttackProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`ATT&CK proxy ${status}`);
  }
}

export async function fetchCatalog(): Promise<AttackCatalog> {
  return jsonRequest<AttackCatalog>("/api/proxy/attack/catalog");
}

export async function fetchLatestAssessment(
  serviceId: string,
): Promise<AttackAssessment | null> {
  try {
    return await jsonRequest<AttackAssessment>(
      `/api/proxy/attack/services/${serviceId}/assessments/latest`,
    );
  } catch (err) {
    if (err instanceof AttackProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function createAssessment(
  serviceId: string,
): Promise<AttackAssessment> {
  return jsonRequest<AttackAssessment>(
    `/api/proxy/attack/services/${serviceId}/assessments`,
    { method: "POST" },
  );
}

export async function patchCoverage(
  coverageId: string,
  patch: AttackCoveragePatch,
): Promise<AttackCoverageRow> {
  return jsonRequest<AttackCoverageRow>(
    `/api/proxy/attack/coverage/${coverageId}`,
    { method: "PATCH", body: patch },
  );
}

/**
 * #101 / #102. The consultant's half of the review queue: "I checked this
 * citation and the resolver got it right." Distinct from `patchCoverage` on
 * purpose — that one says "here is my own answer", and both end up making the
 * row score, so the audit trail has to be able to tell them apart.
 */
export async function confirmCoverageCitations(
  coverageId: string,
): Promise<AttackCoverageRow> {
  return jsonRequest<AttackCoverageRow>(
    `/api/proxy/attack/coverage/${coverageId}/confirm-citations`,
    { method: "POST" },
  );
}

export async function approveAssessment(
  assessmentId: string,
): Promise<AttackAssessment> {
  return jsonRequest<AttackAssessment>(
    `/api/proxy/attack/assessments/${assessmentId}/approve`,
    { method: "POST" },
  );
}

export async function discardAssessment(
  assessmentId: string,
): Promise<AttackAssessment> {
  return jsonRequest<AttackAssessment>(
    `/api/proxy/attack/assessments/${assessmentId}/discard`,
    { method: "POST" },
  );
}

export async function runAttackAi(
  serviceId: string,
): Promise<AttackRunAiResponse> {
  return jsonRequest<AttackRunAiResponse>(
    `/api/proxy/attack/services/${serviceId}/run-ai`,
    { method: "POST" },
  );
}

export async function fetchHeatmap(
  serviceId: string,
): Promise<AttackHeatmap | null> {
  try {
    return await jsonRequest<AttackHeatmap>(
      `/api/proxy/attack/services/${serviceId}/heatmap`,
    );
  } catch (err) {
    if (err instanceof AttackProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function fetchLatestDeliverable(
  serviceId: string,
): Promise<AttackDeliverable | null> {
  try {
    return await jsonRequest<AttackDeliverable>(
      `/api/proxy/attack/services/${serviceId}/deliverables/latest`,
    );
  } catch (err) {
    if (err instanceof AttackProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function finalizeAttackDeliverable(
  serviceId: string,
): Promise<AttackDeliverable> {
  return jsonRequest<AttackDeliverable>(
    `/api/proxy/attack/services/${serviceId}/deliverables/finalize`,
    { method: "POST" },
  );
}

export async function releaseAttackDeliverable(
  deliverableId: string,
): Promise<AttackDeliverable> {
  return jsonRequest<AttackDeliverable>(
    `/api/proxy/attack/deliverables/${deliverableId}/release`,
    { method: "POST" },
  );
}

/**
 * Item 7 part 2. What the mapping will run against, and — the part nothing
 * answered before — what it will NOT.
 *
 * A 404 is NOT swallowed here, unlike `fetchHeatmap` and `fetchLatestDeliverable`.
 * Those 404 when no assessment exists yet, which is an ordinary empty state.
 *
 * Stated as the PROPERTY rather than as a list of sources, so it stays true when
 * another source appears: **this route reads a client's capability membership
 * and needs no assessment at all, so it has no empty-state 404 to distinguish.
 * Every 404 reachable here is therefore a real failure** — a missing service, a
 * wrong `ServiceKind`, a cross-tenant reference, or a caller whose client
 * context cannot be resolved. Some are raised by `current_client` before the
 * handler body runs, so reading `ai_inputs` alone will not show you all of them.
 *
 * Swallowing any of them would render a refusal as "nothing to show", which is
 * the silent-success shape this endpoint exists to end.
 *
 * An earlier draft of this comment enumerated the sources and named only
 * `require_service_in_tenant`. The enumeration was wrong and the decision was
 * right — and a false mechanism in a load-bearing comment reads as authoritative
 * and invites a specific wrong fix, which is what the D-053 correction was
 * about.
 */
export async function fetchAttackAiInputs(
  serviceId: string,
): Promise<AttackAiInputs> {
  return jsonRequest<AttackAiInputs>(
    `/api/proxy/attack/services/${serviceId}/ai-inputs`,
  );
}
