import type { Metadata } from "next";

import { AuditViewer } from "@/components/admin/AuditViewer";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Audit" };

export default function AdminAuditPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Audit" }]} />
      <div>
        <h1 className="text-2xl font-semibold text-ink-primary">Audit log</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Every state-changing action and every AI call, newest first. These are
          append-only records — this view is read-only. Use the correlation link
          to trace an action to the AI call it triggered.
        </p>
      </div>
      <AuditViewer />
    </div>
  );
}
