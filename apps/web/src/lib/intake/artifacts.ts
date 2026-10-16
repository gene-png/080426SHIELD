"use client";

// One rule for an unreadable 2xx across the intake client (#1213).
import { unreadableWrite } from "./client";

export interface ArtifactSummary {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  origin: "client_upload" | "automated_draft" | "consultant_approved";
  stage: string | null;
  uploaded_by: string;
  uploaded_at: string;
  notes: string | null;
}

export interface ArtifactListResponse {
  items: ArtifactSummary[];
}

export class ArtifactUploadError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Upload failed: ${status}`);
  }
}

/**
 * `clientId`, when given, files the upload under that tenant explicitly
 * (#1262): an admin workspace passes its own client, so a document is not
 * stored under whichever client the shared cookie names. The client wizard
 * passes none.
 */
export async function uploadArtifact(
  file: File,
  notes?: string,
  clientId?: string,
): Promise<ArtifactSummary> {
  const form = new FormData();
  form.append("file", file);
  if (notes) form.append("notes", notes);
  const url = clientId
    ? `/api/proxy/artifacts?client_id=${encodeURIComponent(clientId)}`
    : "/api/proxy/artifacts";
  const res = await fetch(url, {
    method: "POST",
    body: form,
  });
  const payload = await safeJson(res);
  if (!res.ok) {
    throw new ArtifactUploadError(res.status, payload);
  }
  if (typeof payload === "string") {
    throw new ArtifactUploadError(res.status, unreadableWrite(res.status));
  }
  return payload as ArtifactSummary;
}

export async function listArtifacts(): Promise<ArtifactListResponse> {
  const res = await fetch("/api/proxy/artifacts", { cache: "no-store" });
  const payload = await safeJson(res);
  if (!res.ok || typeof payload === "string") {
    throw new ArtifactUploadError(res.status, payload);
  }
  return payload as ArtifactListResponse;
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
