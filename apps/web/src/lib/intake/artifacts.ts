"use client";

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

export async function uploadArtifact(
  file: File,
  notes?: string,
): Promise<ArtifactSummary> {
  const form = new FormData();
  form.append("file", file);
  if (notes) form.append("notes", notes);
  const res = await fetch("/api/proxy/artifacts", {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new ArtifactUploadError(res.status, await safeJson(res));
  }
  return (await res.json()) as ArtifactSummary;
}

export async function listArtifacts(): Promise<ArtifactListResponse> {
  const res = await fetch("/api/proxy/artifacts", { cache: "no-store" });
  if (!res.ok) {
    throw new ArtifactUploadError(res.status, await safeJson(res));
  }
  return (await res.json()) as ArtifactListResponse;
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return await res.text();
  }
}
