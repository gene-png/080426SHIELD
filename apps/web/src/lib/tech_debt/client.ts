"use client";

import type {
  CapabilityItem,
  CapabilityItemPatch,
  CapabilityList,
  ConsolidationPlanSummary,
  Deliverable,
  OverlapAnalysis,
  ServiceResponse,
} from "./types";

interface JsonRequestInit {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
}

async function jsonRequest<T>(
  url: string,
  init: JsonRequestInit = {},
): Promise<T> {
  const { body, headers, method = "GET" } = init;
  const res = await fetch(url, {
    method,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let payload: unknown;
    try {
      payload = await res.json();
    } catch {
      payload = await res.text();
    }
    throw new TechDebtProxyError(res.status, payload);
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return (await res.json()) as T;
}

export class TechDebtProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Tech-debt proxy ${status}`);
  }
}

export async function createService(title: string): Promise<ServiceResponse> {
  return jsonRequest<ServiceResponse>("/api/proxy/tech-debt/services", {
    method: "POST",
    body: { kind: "tech_debt", title },
  });
}

export async function extractCapabilities(
  serviceId: string,
  artifactId: string,
): Promise<CapabilityList> {
  return jsonRequest<CapabilityList>(
    `/api/proxy/tech-debt/services/${serviceId}/capability-lists/extract`,
    {
      method: "POST",
      body: { artifact_id: artifactId },
    },
  );
}

export async function fetchLatestList(
  serviceId: string,
): Promise<CapabilityList | null> {
  try {
    return await jsonRequest<CapabilityList>(
      `/api/proxy/tech-debt/services/${serviceId}/capability-lists/latest`,
    );
  } catch (err) {
    if (err instanceof TechDebtProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function patchCapabilityItem(
  itemId: string,
  patch: CapabilityItemPatch,
): Promise<CapabilityItem> {
  return jsonRequest<CapabilityItem>(
    `/api/proxy/tech-debt/capability-items/${itemId}`,
    {
      method: "PATCH",
      body: patch,
    },
  );
}

export async function approveCapabilityList(
  listId: string,
): Promise<CapabilityList> {
  return jsonRequest<CapabilityList>(
    `/api/proxy/tech-debt/capability-lists/${listId}/approve`,
    { method: "POST" },
  );
}

export async function discardCapabilityList(
  listId: string,
): Promise<CapabilityList> {
  return jsonRequest<CapabilityList>(
    `/api/proxy/tech-debt/capability-lists/${listId}/discard`,
    { method: "POST" },
  );
}

export async function fetchConsolidationPlan(
  serviceId: string,
): Promise<ConsolidationPlanSummary | null> {
  try {
    return await jsonRequest<ConsolidationPlanSummary>(
      `/api/proxy/tech-debt/services/${serviceId}/consolidation-plan`,
    );
  } catch (err) {
    if (err instanceof TechDebtProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function fetchOverlapAnalysis(
  serviceId: string,
): Promise<OverlapAnalysis | null> {
  try {
    return await jsonRequest<OverlapAnalysis>(
      `/api/proxy/tech-debt/services/${serviceId}/overlap-analysis`,
    );
  } catch (err) {
    if (err instanceof TechDebtProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function fetchLatestDeliverable(
  serviceId: string,
): Promise<Deliverable | null> {
  try {
    return await jsonRequest<Deliverable>(
      `/api/proxy/tech-debt/services/${serviceId}/deliverables/latest`,
    );
  } catch (err) {
    if (err instanceof TechDebtProxyError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function finalizeDeliverable(
  serviceId: string,
): Promise<Deliverable> {
  return jsonRequest<Deliverable>(
    `/api/proxy/tech-debt/services/${serviceId}/deliverables/finalize`,
    { method: "POST" },
  );
}

export async function releaseDeliverable(
  deliverableId: string,
): Promise<Deliverable> {
  return jsonRequest<Deliverable>(
    `/api/proxy/tech-debt/deliverables/${deliverableId}/release`,
    { method: "POST" },
  );
}
