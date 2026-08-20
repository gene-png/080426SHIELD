import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #30 records the earlier version of this surface as "IN PROGRESS, not done —
 * the render has NO test; `AttackWorkspace.test.tsx` never sets a `runResult`,
 * and `data-testid="attack-citations-rejected"` is referenced nowhere." So the
 * counter shipped, was believed, and nothing checked it rendered at all.
 *
 * These are the tests that were missing.
 */

function result(over: Partial<AttackRunAiResponse> = {}): AttackRunAiResponse {
  return {
    tools_available: 3,
    changed: [],
    coverage: [],
    citations_confirmed: 0,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

describe("AttackCitationAccounting", () => {
  it("states the split on a clean run, so its absence never reads as zero", () => {
    render(
      <AttackCitationAccounting result={result({ citations_confirmed: 7 })} />,
    );
    // Sidesteps the apostrophe: `&rsquo;` renders as U+2019, not "'", so
    // pinning it would assert the HTML entity rather than the copy.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /7 tool citations checked against/,
    );
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /7 confirmed, 0 need review, 0 rejected/,
    );
  });

  it("does not shout about the normal case", () => {
    render(
      <AttackCitationAccounting result={result({ citations_confirmed: 7 })} />,
    );
    // No alert and no warning block when everything matched exactly. Shouting
    // about the common path is how a real warning gets trained away (#31).
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByTestId("attack-citations-review")).toBeNull();
  });

  it("names the tools that were resolved rather than matched", () => {
    render(
      <AttackCitationAccounting
        result={result({
          citations_confirmed: 2,
          citations_needs_review: 1,
          citations_needs_review_tools: ["CrowdStrike Falcon Enterprise"],
        })}
      />,
    );
    expect(screen.getByTestId("attack-citations-review")).toHaveTextContent(
      /CrowdStrike Falcon Enterprise/,
    );
  });

  it("says a flagged citation counts exactly as a confirmed one does", () => {
    // Nothing discounts a flagged citation — 5.1's enforcement is not in W2.
    render(
      <AttackCitationAccounting
        result={result({ citations_needs_review: 1 })}
      />,
    );
    expect(screen.getByTestId("attack-citations-review")).toHaveTextContent(
      /count toward the coverage score exactly as a confirmed citation does/,
    );
  });

  it("singles out a vendor guess made against incomplete vendor data", () => {
    // The nullable-vendor guard computed this reason and NOTHING read it, so a
    // risky vendor guess reported identically to a punctuation rescue. Deleting
    // the guard changed no observable behaviour.
    render(
      <AttackCitationAccounting
        result={result({
          citations_needs_review: 2,
          citations_needs_review_tools: ["Cisco Umbrella", "Tenable.io"],
          citations_needs_review_by_reason: {
            incomplete_vendor_data: ["Cisco Umbrella"],
            punctuation: ["Tenable.io"],
          },
        })}
      />,
    );
    const el = screen.getByTestId("attack-citations-review");
    expect(el).toHaveTextContent(/Cisco Umbrella/);
    expect(el).toHaveTextContent(/matched on a vendor name/);
    expect(el).toHaveTextContent(/riskiest/);
  });

  it("counts entries that were not usable tool names", () => {
    render(
      <AttackCitationAccounting result={result({ citations_unusable: 3 })} />,
    );
    expect(screen.getByTestId("attack-citations-unusable")).toHaveTextContent(
      /3 entries were not usable tool names/,
    );
  });

  it("quotes rejected citations verbatim", () => {
    // "Tenable io" tells a consultant the list holds "Tenable.io". A bare count
    // tells them nothing they can act on.
    render(
      <AttackCitationAccounting
        result={result({
          citations_rejected: 2,
          citations_rejected_examples: ["Tenable io", "Qradar"],
        })}
      />,
    );
    const el = screen.getByTestId("attack-citations-rejected");
    expect(el).toHaveTextContent(/Tenable io/);
    expect(el).toHaveTextContent(/Qradar/);
  });

  it("describes the ACTUAL consequence of a rejection, which is overstated coverage", () => {
    render(
      <AttackCitationAccounting result={result({ citations_rejected: 1 })} />,
    );
    // The first version asserted "reads as uncovered" — the INVERSE of what the
    // route does. `run_ai` assigns `row.status` independently of citations, so
    // the technique keeps `covered` with an empty tool list and carries full
    // weight in coverage_pct and the client PDF.
    const el = screen.getByTestId("attack-citations-rejected");
    expect(el).toHaveTextContent(/keeps whatever status the model gave it/);
    expect(el).toHaveTextContent(
      /can still read as covered with nothing behind it/,
    );
    expect(el).not.toHaveTextContent(/reads as uncovered/);
  });

  it("uses role=alert only for the outcome that loses evidence", () => {
    render(
      <AttackCitationAccounting result={result({ citations_rejected: 1 })} />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("caps a long list and says how many it omitted", () => {
    const many = Array.from({ length: 14 }, (_, i) => `Tool ${i}`);
    render(
      <AttackCitationAccounting
        result={result({
          citations_needs_review: 14,
          citations_needs_review_tools: many,
        })}
      />,
    );
    const el = screen.getByTestId("attack-citations-review");
    expect(el).toHaveTextContent(/Tool 9/);
    expect(el).toHaveTextContent(/and 4 more/);
    expect(el).not.toHaveTextContent(/Tool 10/);
  });

  it("renders nothing for a run from before the resolver existed", () => {
    // A stored payload with none of these fields never measured citations.
    // Rendering "0 citations" over it would assert something the run did not do.
    const { container } = render(
      <AttackCitationAccounting
        result={{ tools_available: 3, changed: [], coverage: [] }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("singularises one citation", () => {
    render(
      <AttackCitationAccounting result={result({ citations_confirmed: 1 })} />,
    );
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /^1 tool citation checked/,
    );
  });
});
