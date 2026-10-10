import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackOmittedTechnique,
  AttackRunAiResponse,
} from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #853: the techniques a successful Run-AI batch was asked about and got no
 * entry for. Copy A1 to A4 approved verbatim (#736 comment 6090870696). Every
 * expected string below is a literal typed from that ruling, never read from
 * the component.
 */
function result(over: Partial<AttackRunAiResponse>): AttackRunAiResponse {
  return {
    tools_available: 3,
    changed: [],
    coverage: [],
    citations_confirmed: 4,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

function unscored(n: number): AttackOmittedTechnique[] {
  return Array.from({ length: n }, (_, i) => ({
    technique_code: `T${1100 + i}`,
    kept_status: null,
  }));
}

function omitted(
  items: AttackOmittedTechnique[],
): Partial<AttackRunAiResponse> {
  return { omitted_count: items.length, omitted_techniques: items };
}

function texts(el: HTMLElement): string[] {
  return within(el)
    .getAllByRole("listitem")
    .map((li) => li.textContent ?? "");
}

const A4 =
  "Check these before approving. A status kept this way was not confirmed by this run and reaches the coverage figures and the deliverable as it is. Run AI again, or set the status in the technique panel.";

describe("AttackCitationAccounting: techniques the AI left out (#853)", () => {
  it.each([
    ["zero", { omitted_count: 0, omitted_techniques: [] }],
    ["absent (a run stored before #853)", {}],
  ])("renders nothing when the count is %s", (_label, over) => {
    render(<AttackCitationAccounting result={result(over)} />);
    // The positive state first: the panel rendered.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /4 tool citations checked against/,
    );
    expect(screen.queryByTestId("attack-omitted")).toBeNull();
    expect(screen.queryByText(/got no status from the AI/)).toBeNull();
  });

  it("A1, singular", () => {
    render(<AttackCitationAccounting result={result(omitted(unscored(1)))} />);
    expect(screen.getByTestId("attack-omitted-count").textContent).toBe(
      "1 technique got no status from the AI this run.",
    );
  });

  it("A1, plural", () => {
    render(<AttackCitationAccounting result={result(omitted(unscored(3)))} />);
    expect(screen.getByTestId("attack-omitted-count").textContent).toBe(
      "3 techniques got no status from the AI this run.",
    );
  });

  it("renders when the batch returned nothing at all", () => {
    render(
      <AttackCitationAccounting
        result={result({
          citations_confirmed: 0,
          ...omitted(unscored(2)),
        })}
      />,
    );
    expect(screen.getByTestId("attack-omitted-count").textContent).toBe(
      "2 techniques got no status from the AI this run.",
    );
  });

  it("A2 lists at most ten, then 'and {rest} more'", () => {
    render(<AttackCitationAccounting result={result(omitted(unscored(12)))} />);
    const group = screen.getByTestId("attack-omitted-unscored");
    expect(group.querySelector("p")?.textContent).toBe(
      "No status before this run, so still unscored (12):",
    );
    expect(texts(group)).toEqual([
      "T1100",
      "T1101",
      "T1102",
      "T1103",
      "T1104",
      "T1105",
      "T1106",
      "T1107",
      "T1108",
      "T1109",
      "and 2 more",
    ]);
  });

  it("A2 at exactly ten has no 'more' line", () => {
    render(<AttackCitationAccounting result={result(omitted(unscored(10)))} />);
    const items = texts(screen.getByTestId("attack-omitted-unscored"));
    expect(items).toHaveLength(10);
    expect(items[9]).toBe("T1109");
  });

  it("A3 names each kept status with its label, and A4 follows", () => {
    render(
      <AttackCitationAccounting
        result={result(
          omitted([
            { technique_code: "T1005", kept_status: "gap" },
            { technique_code: "T1059", kept_status: "covered" },
            { technique_code: "T1078", kept_status: "partial" },
            { technique_code: "T1190", kept_status: null },
          ]),
        )}
      />,
    );
    const kept = screen.getByTestId("attack-omitted-kept-list");
    expect(kept.querySelector("p")?.textContent).toBe(
      "Kept the status it had (3):",
    );
    expect(texts(kept)).toEqual([
      "T1005 (Gap)",
      "T1059 (Covered)",
      "T1078 (Partial)",
    ]);
    expect(texts(screen.getByTestId("attack-omitted-unscored"))).toEqual([
      "T1190",
    ]);
    expect(screen.getByTestId("attack-omitted-check").textContent).toBe(A4);
  });

  it("A3 caps at ten as well", () => {
    const items = Array.from({ length: 11 }, (_, i) => ({
      technique_code: `T${1200 + i}`,
      kept_status: "gap" as const,
    }));
    render(<AttackCitationAccounting result={result(omitted(items))} />);
    const list = texts(screen.getByTestId("attack-omitted-kept-list"));
    expect(list).toHaveLength(11);
    expect(list[9]).toBe("T1209 (Gap)");
    expect(list[10]).toBe("and 1 more");
  });

  it("A4 is absent when nothing kept a status", () => {
    render(<AttackCitationAccounting result={result(omitted(unscored(2)))} />);
    // The positive state first: the omitted block rendered.
    expect(screen.getByTestId("attack-omitted-unscored")).toBeVisible();
    expect(screen.queryByTestId("attack-omitted-check")).toBeNull();
    expect(screen.queryByText(/Check these before approving/)).toBeNull();
    expect(screen.queryByTestId("attack-omitted-kept")).toBeNull();
  });

  const keptOne = omitted([{ technique_code: "T1005", kept_status: "gap" }]);

  it("A3 and A4 are the alert when no batch failed", () => {
    render(<AttackCitationAccounting result={result(keptOne)} />);
    const region = screen.getByTestId("attack-omitted-kept");
    expect(region.getAttribute("role")).toBe("alert");
    expect(within(region).getByTestId("attack-omitted-kept-list")).toBeTruthy();
    expect(within(region).getByTestId("attack-omitted-check").textContent).toBe(
      A4,
    );
    expect(screen.queryByTestId("attack-run-incomplete")).toBeNull();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("A3 and A4 are a status beside the failed-batch alert", () => {
    render(
      <AttackCitationAccounting
        result={result({ batches_total: 3, batches_failed: 1, ...keptOne })}
      />,
    );
    expect(
      screen.getByTestId("attack-run-incomplete").getAttribute("role"),
    ).toBe("alert");
    const region = screen.getByTestId("attack-omitted-kept");
    expect(region.getAttribute("role")).toBe("status");
    expect(within(region).getByTestId("attack-omitted-check").textContent).toBe(
      A4,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  // "The panel's only alert": the rejected-citations line is the panel's other
  // role="alert", so beside it A3 and A4 are a status too.
  it("A3 and A4 are a status beside the rejected-citations alert", () => {
    render(
      <AttackCitationAccounting
        result={result({ citations_rejected: 1, ...keptOne })}
      />,
    );
    expect(
      screen.getByTestId("attack-citations-rejected").getAttribute("role"),
    ).toBe("alert");
    expect(screen.getByTestId("attack-omitted-kept").getAttribute("role")).toBe(
      "status",
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("sits immediately after the failed-batch alert", () => {
    render(
      <AttackCitationAccounting
        result={result({ batches_total: 3, batches_failed: 1, ...keptOne })}
      />,
    );
    expect(screen.getByTestId("attack-run-incomplete").nextElementSibling).toBe(
      screen.getByTestId("attack-omitted"),
    );
  });
});
