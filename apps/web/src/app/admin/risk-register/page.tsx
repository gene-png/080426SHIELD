import type { Metadata } from "next";
import { Suspense } from "react";

import { RiskRegisterDashboard } from "@/components/admin/risk/RiskRegisterDashboard";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Risk Register" };

export default function RiskRegisterPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Risk Register" }]} />
      {/* RR-2 (for #1121): `useSearchParams` needs a Suspense boundary
          during static render. The admin layout is dynamic, so this is belt
          and braces; the fallback keeps the page's h1. */}
      <Suspense
        fallback={
          <h1 className="text-2xl font-semibold text-ink-primary">
            Risk Register
          </h1>
        }
      >
        <RiskRegisterDashboard />
      </Suspense>
    </div>
  );
}
