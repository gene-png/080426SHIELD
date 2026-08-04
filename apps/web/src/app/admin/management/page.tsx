import type { Metadata } from "next";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import { LlmKeyPanel } from "@/components/admin/LlmKeyPanel";
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
          Create client companies, approve the email domains their teams use to
          register, manage user access, and configure the AI provider key.
        </p>
      </div>

      {/* Issue 2: the anchor the offline banner and the Run-AI prompt link to. */}
      <Card id="ai-provider-key">
        <CardHeader>
          <CardTitle>AI provider key</CardTitle>
          <CardDescription>
            Without a key, every AI step returns a deterministic offline
            response instead of analysing the client&apos;s data.
          </CardDescription>
        </CardHeader>
        <CardBody>
          <LlmKeyPanel />
        </CardBody>
      </Card>

      <ManagementView />
    </div>
  );
}
