import type { Metadata } from "next";

import { CsfWorkspace } from "@/components/admin/csf/CsfWorkspace";
import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "NIST CSF 2.0 service",
};

export default async function CsfServicePage(props: {
  params: Promise<{ id: string }>;
}): Promise<JSX.Element> {
  const params = await props.params;
  return (
    <EnsureActiveClient serviceId={params.id}>
      <CsfWorkspace
        serviceId={params.id}
        serviceTitle="NIST CSF 2.0 Assessment"
      />
    </EnsureActiveClient>
  );
}
