import type { Metadata } from "next";
import { Suspense } from "react";

import { DeliverablesTable } from "@/components/admin/DeliverablesTable";
import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Deliverables" };

/**
 * IA appendix: one place showing every deliverable for one tenant, released
 * or not. Scoped by the page's own client picker (`?client=`), like the Risk
 * Register and Messages (RR-2, for #1121), not by the active-client cookie.
 */
export default function AdminDeliverablesPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Deliverables" }]} />
      {/* RR-2 (for #1121): `useSearchParams` needs a Suspense boundary
          during static render. The admin layout is dynamic, so this is belt
          and braces; the fallback keeps the page's h1. */}
      <Suspense
        fallback={
          <h1 className="text-3xl font-semibold text-ink-primary">
            Deliverables
          </h1>
        }
      >
        <DeliverablesTable />
      </Suspense>
    </div>
  );
}
