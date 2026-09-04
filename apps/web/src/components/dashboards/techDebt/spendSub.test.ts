/**
 * The sentence the CLIENT actually reads about their own spend figure.
 *
 * #126's API half is thoroughly tested; this half was pinned by nothing.
 * `spendSub` was not exported, `techDebt.test.ts` never mentioned
 * `spend_completeness`, and the card label is deliberately unchanged so
 * `s29-tech-debt-dashboard.spec.ts` cannot see the subtitle either. Deleting
 * the "partial" and "unknown" branches left vitest, s29 and the whole backend
 * suite green -- a tri-state computed carefully on the server and rendered by
 * a function no test could fail on.
 *
 * Every branch is covered, including the "complete" one: a guard that
 * qualified every figure would satisfy the negative assertions alone, which is
 * the shape #102 records.
 */
import { describe, expect, it } from "vitest";

import { spendSub } from "./TechDebtDashboard";
import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

function data(over: Partial<TechDebtDashboardData>): TechDebtDashboardData {
  return {
    spend_completeness: "complete",
    excluded_count: 0,
    source_rows_total: 10,
    // Balanced by default: included == source rows. A default that did NOT
    // balance would put every case below into the unbalanced branch and the
    // suite would be describing an impossible world -- the same fixture defect
    // that hid this state in `test_tech_debt_dashboard.py`.
    //
    // Cases that override `excluded_count` or `source_rows_total` without also
    // setting `included_count` are NOT internally consistent with the API's
    // derivation (`excluded_count = max(source_rows_total - included_count, 0)`).
    // That is deliberate and harmless HERE -- `spendSub` reads the fields it is
    // given and never re-derives them -- but it means this helper builds inputs
    // to the renderer, not states the API can actually emit. Said out loud so
    // nobody reads a passing case as proof the backend can produce it.
    included_count: 10,
    ...over,
  } as TechDebtDashboardData;
}

describe("spendSub", () => {
  it("says nothing qualifying when the figure really is complete", () => {
    // POSITIVE CONTROL. Without this every other case below is satisfied by a
    // function that returns a caveat unconditionally.
    expect(spendSub(data({ spend_completeness: "complete" }))).toBe(
      "Across all tools",
    );
  });

  it("names the unreconciled upload rather than implying a total", () => {
    expect(spendSub(data({ spend_completeness: "unknown" }))).toBe(
      "May not be complete - upload not reconciled",
    );
  });

  it("counts the excluded rows when it can", () => {
    expect(
      spendSub(
        data({
          spend_completeness: "partial",
          excluded_count: 3,
          source_rows_total: 12,
        }),
      ),
    ).toBe("Floor - 3 of 12 uploaded rows excluded");
  });

  it("falls back to the uncosted-tool wording when no rows were excluded", () => {
    expect(
      spendSub(data({ spend_completeness: "partial", excluded_count: 0 })),
    ).toBe("Floor - some tools lacked a cost");
  });

  it("does not claim a row count it does not have", () => {
    // `excluded_count > 0` with a NULL `source_rows_total` is the state where
    // the count cannot be expressed as "N of M". Rendering "3 of null" is the
    // failure this guards.
    const out = spendSub(
      data({
        spend_completeness: "partial",
        excluded_count: 3,
        source_rows_total: null,
      }),
    );
    expect(out).toBe("Floor - some tools lacked a cost");
    expect(out).not.toContain("null");
  });

  it("never calls a partial or unknown figure complete", () => {
    for (const c of ["partial", "unknown"] as const) {
      expect(spendSub(data({ spend_completeness: c }))).not.toBe(
        "Across all tools",
      );
    }
  });
});

describe("spendSub, the fourth state", () => {
  it("does not claim an uncosted tool when the upload simply does not reconcile", () => {
    // The API reports "partial" for this state with `excluded_count` floored to
    // 0 and every cost present. Rendering "some tools lacked a cost" here is a
    // checkable falsehood -- the client goes looking for an uncosted tool and
    // finds none. This is the one branch a three-valued label cannot express,
    // so the renderer recovers it from the two counts.
    const out = spendSub(
      data({
        spend_completeness: "partial",
        excluded_count: 0,
        source_rows_total: 30,
        included_count: 31,
      }),
    );
    expect(out).toBe("Floor - upload does not reconcile");
    expect(out).not.toContain("lacked a cost");
  });

  it("still says 'lacked a cost' when that is actually the cause", () => {
    // POSITIVE CONTROL for the branch above: a balanced list with an uncosted
    // item must keep the original wording, or the new branch has simply
    // replaced one wrong sentence with another.
    expect(
      spendSub(
        data({
          spend_completeness: "partial",
          excluded_count: 0,
          source_rows_total: 30,
          included_count: 30,
        }),
      ),
    ).toBe("Floor - some tools lacked a cost");
  });
});
