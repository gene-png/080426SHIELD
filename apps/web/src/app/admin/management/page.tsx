import type { Metadata } from "next";

import { ManagementView } from "@/components/admin/ManagementView";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Management" };

export default function ManagementPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Management" }]} />
      <div>
        <h1 className="text-2xl font-semibold text-ink-primary">Management</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Create client companies and approve the email domains their teams use
          to register.
        </p>
      </div>
      <ManagementView />
    </div>
  );
}
