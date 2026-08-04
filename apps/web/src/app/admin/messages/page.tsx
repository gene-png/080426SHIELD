import type { Metadata } from "next";

import { InboxView } from "@/components/admin/InboxView";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Messages" };

export default function AdminMessagesPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Messages" }]} />
      <div>
        <h1 className="text-2xl font-semibold text-ink-primary">Messages</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Threads for the selected client, newest first. The badge counts
          messages you haven&apos;t opened yet.
        </p>
      </div>
      <InboxView />
    </div>
  );
}
