import { HealthMatrix } from "@/components/admin/HealthMatrix";

import type { JSX } from "react";

/**
 * Operator view for the `/ready` dependency matrix (Sprint 6 T3). Role
 * enforcement lives in the admin layout; the proxy re-checks admin too.
 */
export default function AdminHealthPage(): JSX.Element {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink-primary">
          System health
        </h1>
        <p className="mt-1 text-sm text-ink-secondary">
          Live readiness of every downstream dependency. Required dependencies
          flip the deployment to degraded; keycloak and fixture-mode AI are
          informational.
        </p>
      </header>
      <HealthMatrix />
    </div>
  );
}
