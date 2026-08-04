import type { Metadata } from "next";

import { RiskRegisterDashboard } from "@/components/admin/risk/RiskRegisterDashboard";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Risk Register" };

export default function RiskRegisterPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Risk Register" }]} />
      <RiskRegisterDashboard />
    </div>
  );
}
