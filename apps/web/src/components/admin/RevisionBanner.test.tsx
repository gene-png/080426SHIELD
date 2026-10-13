import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RevisionBanner } from "./RevisionBanner";

import type { RevisionInfo } from "@/lib/revisions/types";

const BASE: RevisionInfo = {
  from_version: 2,
  started_by_name: "Dana Reyes",
  started_at: "2026-10-13T09:00:00Z",
  reason: "Client found a typo",
  rules_changed: false,
  retired_codes: [],
};
const DATE = new Date(BASE.started_at).toLocaleDateString();

describe("RevisionBanner (#1120)", () => {
  it("says who started the revision, when and why (V5)", () => {
    render(<RevisionBanner status="draft" revision={BASE} />);
    expect(
      screen.getByText(
        `Revision of version 2, started by Dana Reyes on ${DATE}: Client found a typo.`,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/current scoring rules/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ATT&CK catalog/)).not.toBeInTheDocument();
  });

  it("says the rules changed when the source was approved under earlier ones (V3)", () => {
    render(
      <RevisionBanner
        status="draft"
        revision={{ ...BASE, rules_changed: true }}
      />,
    );
    expect(
      screen.getByText(
        "This revision uses the current scoring rules. Version 2 was approved under earlier rules, so some results may differ from what the client has.",
      ),
    ).toBeInTheDocument();
  });

  it("names one dropped technique in the singular (V4)", () => {
    render(
      <RevisionBanner
        status="draft"
        revision={{ ...BASE, retired_codes: ["T1001"] }}
      />,
    );
    expect(
      screen.getByText(
        "This revision uses the current ATT&CK catalog. 1 technique from version 2 is no longer in it and was not copied: T1001.",
      ),
    ).toBeInTheDocument();
  });

  it("names several dropped techniques in the plural (V4)", () => {
    render(
      <RevisionBanner
        status="draft"
        revision={{ ...BASE, retired_codes: ["T1001", "T1002"] }}
      />,
    );
    expect(
      screen.getByText(
        "This revision uses the current ATT&CK catalog. 2 techniques from version 2 are no longer in it and were not copied: T1001, T1002.",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    ["approved", BASE],
    ["draft", null],
  ] as const)(
    "renders nothing for status %s without a revision draft",
    (status, revision) => {
      const { container } = render(
        <RevisionBanner status={status} revision={revision} />,
      );
      expect(container).toBeEmptyDOMElement();
    },
  );
});
