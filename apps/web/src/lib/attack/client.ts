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

/** What the mapping will run against — capabilities, lists and source documents. */
export async function fetchAttackAiInputs(
  serviceId: string,
): Promise<AttackAiInputs> {
  return jsonRequest<AttackAiInputs>(
    `/api/proxy/attack/services/${serviceId}/ai-inputs`,
    { method: "GET" },
  );
}
