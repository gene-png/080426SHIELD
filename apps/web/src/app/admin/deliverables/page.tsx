import type { Metadata } from "next";

import { DeliverablesTable } from "@/components/admin/DeliverablesTable";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Deliverables" };

/**
 * IA appendix: one place showing every deliverable for the active tenant,
 * released or not. Scoped by the active-client cookie, like the Risk Register.
 */
export default function AdminDeliverablesPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Deliverables" }]} />
      <DeliverablesTable />
    </div>
  );
}
