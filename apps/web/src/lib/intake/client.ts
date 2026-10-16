"use client";

import {
  UPSTREAM_OUTCOME_UNKNOWN,
  UPSTREAM_OUTCOME_UNKNOWN_MESSAGE,
} from "@/lib/upstream-outcome";

import type {
  AssessmentCreateRequest,
  AssessmentResponse,
  IntakePatchRequest,
  IntakeStateResponse,
  IntakeSubmitRequest,
} from "./types";

/**
 * Client-side wrappers that call the same-origin proxy routes. The proxy
 * (apps/web/src/app/api/proxy/intake/...) attaches the user's bearer
 * token server-side, keeping the API host name and the access token off
 * the wire to the browser.
 */

class ProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Intake proxy ${status}`);
  }
}

export async function fetchIntake(): Promise<IntakeStateResponse> {
  const res = await fetch("/api/proxy/intake", { cache: "no-store" });
  const payload = await safeJson(res);
  if (!res.ok || typeof payload === "string") {
    throw new ProxyError(res.status, payload);
  }
  return payload as IntakeStateResponse;
}

export async function patchIntake(
  body: IntakePatchRequest,
): Promise<IntakeStateResponse> {
  const res = await fetch("/api/proxy/intake", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await safeJson(res);
  if (!res.ok) {
    throw new ProxyError(res.status, payload);
  }
  // #1093 item 2: a 2xx whose body is not JSON. Thrown with its status, so
  // the caller can tell it from no answer at all; a bare parse error carried
  // none and read as "Network error.". The proxy never sends one, so the hook
  // calls its outcome unknown.
  if (typeof payload === "string") {
    throw new ProxyError(res.status, payload);
  }
  return payload as IntakeStateResponse;
}

export async function submitIntake(
  body: IntakeSubmitRequest,
): Promise<IntakeStateResponse> {
  const res = await fetch("/api/proxy/intake/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await safeJson(res);
  if (!res.ok) {
    throw new ProxyError(res.status, payload);
  }
  if (typeof payload === "string") {
    throw new ProxyError(res.status, unreadableWrite(res.status));
  }
  return payload as IntakeStateResponse;
}

export async function fetchAssessments(): Promise<AssessmentResponse[]> {
  const res = await fetch("/api/proxy/intake/assessments", {
    cache: "no-store",
  });
  const payload = await safeJson(res);
  if (!res.ok || typeof payload === "string") {
    throw new ProxyError(res.status, payload);
  }
  return payload as AssessmentResponse[];
}

export async function createAssessment(
  body: AssessmentCreateRequest,
): Promise<AssessmentResponse> {
  const res = await fetch("/api/proxy/intake/assessments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await safeJson(res);
  if (!res.ok) {
    throw new ProxyError(res.status, payload);
  }
  if (typeof payload === "string") {
    throw new ProxyError(res.status, unreadableWrite(res.status));
  }
  return payload as AssessmentResponse;
}

/**
 * #1213 (#1093 item 2's rule): a 2xx whose body is not JSON. The intake
 * proxies answer a 2xx with JSON (the intake routes re-serialise it, and turn
 * an api 2xx they cannot read into the typed 504; the artifacts route passes
 * the api's body through, and the api answers it with JSON), so this came
 * from something in front of the app (a captive portal, a proxy's block page)
 * and the request may never have arrived. A WRITE's outcome is therefore
 * unknown: it is thrown carrying the #550 envelope, so a caller that renders
 * through `clientFacingError` shows the approved sentence, never its own
 * failure copy and never success. A READ changed nothing, so it is thrown with
 * its status and the raw body, for the caller to report as a failed load.
 */
export function unreadableWrite(status: number): { error: object } {
  return {
    error: {
      code: status,
      reason: UPSTREAM_OUTCOME_UNKNOWN,
      message: UPSTREAM_OUTCOME_UNKNOWN_MESSAGE,
    },
  };
}

async function safeJson(res: Response): Promise<unknown> {
  // Read the body ONCE; see the note in `lib/api.ts`. `res.json()` consumes
  // the stream even when it throws, so the `res.text()` fallback raises
  // "body stream already read" and that TypeError escapes in place of the
  // value this function exists to return.
  const raw = await res.text();
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

export { ProxyError };
