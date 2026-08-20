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

  it("says a flagged citation STILL counts toward the score", () => {
    // 5.1's enforcement is on the technique status and is not part of W2. If the
    // copy left that out, a consultant would reasonably assume a flagged
    // citation had already been discounted — a surfaced number implying more
    // than it does, which is the defect this codebase keeps fixing.
    render(
      <AttackCitationAccounting
        result={result({ citations_needs_review: 1 })}
      />,
    );
    expect(screen.getByTestId("attack-citations-review")).toHaveTextContent(
      /still count toward the coverage score/,
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

  it("explains the consequence of a rejection rather than just counting it", () => {
    render(
      <AttackCitationAccounting result={result({ citations_rejected: 1 })} />,
    );
    expect(screen.getByTestId("attack-citations-rejected")).toHaveTextContent(
      /reads as uncovered/,
    );
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
