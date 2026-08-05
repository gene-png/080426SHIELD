import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";

export async function GET(request: Request): Promise<NextResponse> {
  const session = await auth();
  const bearer = session?.accessToken;
  if (!bearer) {
    return NextResponse.json(
      { error: { code: 401, message: "Not signed in." } },
      { status: 401 },
    );
  }
  // Issue 7: scope the queue to one organization when the org index links here.
  const clientId = new URL(request.url).searchParams.get("client_id");
  const path = clientId
    ? `/admin/intake-queue?client_id=${encodeURIComponent(clientId)}`
    : "/admin/intake-queue";
  try {
    const result = await apiFetch<unknown>(path, { bearer });
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(err.payload ?? { error: { code: err.status } }, {
        status: err.status,
      });
    }
    return NextResponse.json(
      { error: { message: "Upstream admin call failed." } },
      { status: 502 },
    );
  }
}
