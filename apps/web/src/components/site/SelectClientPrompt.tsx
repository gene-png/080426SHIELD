import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import type { JSX } from "react";

export interface SelectClientPromptProps {
  /** Trailing verb phrase for the heading, e.g. "start the intake". */
  action?: string;
}

/**
 * Friendly stand-in for the backend's raw 400 "X-Client-Id header is required"
 * response. Admin users are not tied to a single tenant, so tenant-
 * scoped pages need them to pick an active client first. Pure markup so it can
 * render in both server and client components.
 */
export function SelectClientPrompt({
  action = "continue",
}: SelectClientPromptProps): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Select a client to {action}</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="text-sm text-ink-secondary">
          You&apos;re signed in as a platform user that isn&apos;t tied to a
          single client. Use the{" "}
          <span className="font-medium text-ink-primary">client switcher</span>{" "}
          in the top navigation to choose which client you&apos;re working on,
          and this page will load.
        </p>
      </CardBody>
    </Card>
  );
}
