import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardBody } from "@shield/design-system";

import { Breadcrumbs } from "@/components/site/Breadcrumbs";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Active Work" };

export default function ActiveWorkPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: "Active Work" }]} />
      <div>
        <h1 className="text-2xl font-semibold text-ink-primary">Active Work</h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Assessments currently in analysis across all clients.
        </p>
      </div>
      <Card>
        <CardBody className="flex flex-col items-start gap-3">
          <p className="text-sm text-ink-secondary">
            Open a workspace from the intake queue once you publish a request
            for processing. A consolidated active-work list lands with the
            service dashboards.
          </p>
          <Link
            href="/admin/queue"
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Go to the intake queue
          </Link>
        </CardBody>
      </Card>
    </div>
  );
}
