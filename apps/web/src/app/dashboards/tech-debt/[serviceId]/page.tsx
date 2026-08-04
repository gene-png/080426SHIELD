import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { TechDebtDashboard } from "@/components/dashboards/techDebt/TechDebtDashboard";
import { ACTIVE_CLIENT_COOKIE, ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Software Portfolio Dashboard" };

interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
}

export default async function TechDebtDashboardPage({
  params,
}: {
  params: Promise<{ serviceId: string }>;
}): Promise<JSX.Element> {
  const { serviceId } = await params;
  const session = await auth();
  if (!session?.accessToken) {
    redirect(`/sign-in?callbackUrl=/dashboards/tech-debt/${serviceId}`);
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

  let data: TechDebtDashboardData | null = null;
  let notReleased = false;
  if (clientId) {
    try {
      data = await apiFetch<TechDebtDashboardData>(
        `/clients/${clientId}/tech-debt/${serviceId}/dashboard`,
        { bearer: token },
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
          Dashboard not available yet
        </h1>
        <p className="text-sm text-ink-secondary">
          {notReleased
            ? "This Technical Debt report hasn't been released to your organization yet. It will appear here once your SHIELD analyst releases it."
            : "We couldn't load this dashboard."}
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

  return <TechDebtDashboard data={data} />;
}
