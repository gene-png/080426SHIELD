import type { Metadata } from "next";

import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";
import { ZtWorkspace } from "@/components/admin/zt/ZtWorkspace";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Zero Trust (DoD ZTRA) service",
};

export default async function ZtDodServicePage(props: {
  params: Promise<{ id: string }>;
}): Promise<JSX.Element> {
  const params = await props.params;
  return (
    <EnsureActiveClient serviceId={params.id}>
      <ZtWorkspace
        serviceId={params.id}
        framework="dod_ztra"
        serviceTitle="Zero Trust Assessment — DoD Reference Architecture"
      />
    </EnsureActiveClient>
  );
}
