import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import type { JSX } from "react";

/**
 * Plain-English disclosure explaining what happens to uploaded documents.
 *
 * Master Spec §12 risk acceptance: SHIELD v1 uses a commercial LLM
 * provider. Egress is gated by a mandatory redactor. This component is
 * the user-facing copy of that policy; the redactor module itself
 * (`apps/api/app/ai/redact.py`) ships in Phase 3.
 */
export function RedactionDisclosure(): JSX.Element {
  return (
    <Card variant="flat" className="bg-status-info-bg">
      <CardHeader>
        <CardTitle className="text-base text-status-info-fg">
          What happens to documents you upload
        </CardTitle>
      </CardHeader>
      <CardBody>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-status-info-fg">
          <li>
            Documents are stored inside this deployment and never shared with
            another customer.
          </li>
          <li>
            Before any AI-assisted analysis, a redaction step removes personal
            information (names, email addresses, phone numbers, addresses), your
            organization name, and identifiers like SSNs, EINs, CAGE codes, and
            contract numbers. The redacted version is what reaches the AI
            provider.
          </li>
          <li>
            A Kentro consultant reviews and approves the redacted version before
            the first AI call for a new service. You can request a copy of the
            redacted preview at any time.
          </li>
          <li>
            Every AI call writes an audit row with the count of items removed by
            the redactor — no payload contents.
          </li>
        </ul>
      </CardBody>
    </Card>
  );
}
