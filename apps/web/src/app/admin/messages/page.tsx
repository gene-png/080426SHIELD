import type { Metadata } from "next";
import { Suspense } from "react";

import { InboxView } from "@/components/admin/InboxView";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Messages" };

export default function AdminMessagesPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Messages" }]} />
      {/* RR-2 (for #1121): the h1 and subtitle depend on the chosen client,
          so they live in InboxView. `useSearchParams` needs a Suspense
          boundary during static render; the fallback keeps the page's h1. */}
      <Suspense
        fallback={
          <h1 className="text-2xl font-semibold text-ink-primary">Messages</h1>
        }
      >
        <InboxView />
      </Suspense>
    </div>
  );
}
