import type { Metadata } from "next";

import { AttackWorkspace } from "@/components/admin/attack/AttackWorkspace";
import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "MITRE ATT&CK Coverage service",
};

export default async function AttackCoverageServicePage(props: {
  params: Promise<{ id: string }>;
}): Promise<JSX.Element> {
  const params = await props.params;
  return (
    <EnsureActiveClient serviceId={params.id}>
      <AttackWorkspace
        serviceId={params.id}
        serviceTitle="MITRE ATT&CK Coverage"
      />
    </EnsureActiveClient>
  );
}
