import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { RiskDashboard } from "@/components/dashboards/risk/RiskDashboard";
import { ACTIVE_CLIENT_COOKIE, ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Risk Register Dashboard" };

interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
}

export default async function RiskDashboardPage(): Promise<JSX.Element> {
  const session = await auth();
  if (!session?.accessToken) {
    redirect(`/sign-in?callbackUrl=/dashboards/risk`);
  }
  const token = session.accessToken;

  const me = await apiFetch<MeResponse>("/auth/me", {
    bearer: token,
    clientId: "",
  });
  let clientId = me.client_id ?? undefined;
  if (!clientId) {
    clientId = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value ?? undefined;
  }

  let data: RiskDashboardData | null = null;
  let notReleased = false;
  if (clientId) {
    try {
      data = await apiFetch<RiskDashboardData>(
        `/clients/${clientId}/risk/dashboard`,
        {
          bearer: token,
        },
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notReleased = true;
      } else {
        throw err;
      }
    }
  } else {
    notReleased = true;
  }

  if (!data) {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-16">
        <h1 className="text-2xl font-semibold text-ink-primary">
          Risk Register not available yet
        </h1>
        <p className="text-sm text-ink-secondary">
          {notReleased
            ? "Your Risk Register hasn't been finalized yet. It will appear here once your SHIELD analyst generates and finalizes it."
            : "We couldn't load your Risk Register."}
        </p>
        <Link
          href="/documents"
          className="text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          ← Back to documents
        </Link>
      </main>
    );
  }

  return <RiskDashboard data={data} />;
}
