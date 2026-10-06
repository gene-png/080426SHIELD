import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #758's review findings, driven through the REAL `CsfQuestionnaire` -- its
 * `TierPicker` and its notes textarea, with the textarea's trim,
 * no-op-if-unchanged and remount-on-confirmed-value behaviour. The file
 * beside this one stands in for the questionnaire, so it cannot see what the
 * questionnaire does while Submit is out, nor that a row's two fields save
 * separately.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

/** What `lib/csf/client.ts` throws: an error with `status` and `payload`. */
function proxyError(status: number, payload: unknown): Error {
  return Object.assign(new Error(`CSF proxy ${status}`), { status, payload });
}

/** The api's own 500 envelope, `exceptions.py`'s `_handle_unexpected`. */
const SERVER_ERROR = () =>
  proxyError(500, {
    error: {
      code: 500,
      message: "An internal error occurred. Please contact support.",
    },
  });

const CATALOG: CsfCatalog = {
  functions: [
    {
      code: "GV",
      name: "Govern",
      purpose: "Set direction.",
      categories: [
        {
          code: "GV.OC",
          function: "GV",
          name: "Organizational Context",
          purpose: "Know the mission.",
          subcategories: [
            {
              code: "GV.OC-01",
              function: "GV",
              category: "GV.OC",
              name: "Mission",
              outcome: "The mission is understood.",
              min_profile: "LOW",
            },
            {
              code: "GV.OC-02",
              function: "GV",
              category: "GV.OC",
              name: "Stakeholders",
              outcome: "Stakeholders are understood.",
              min_profile: "LOW",
            },
          ],
        },
      ],
    },
  ],
  tiers: [
    { tier: 1, short_label: "Partial", description: "" },
    { tier: 2, short_label: "Risk Informed", description: "" },
    { tier: 3, short_label: "Repeatable", description: "" },
    { tier: 4, short_label: "Adaptive", description: "" },
  ],
  total_subcategories: 2,
};

function answer(
  id: string,
  code: string,
  tier: number | null,
  notes: string | null,
): CsfAnswer {
  return {
    id,
    assessment_id: "a1",
    subcategory_code: code,
    maturity_tier: tier,
    notes,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
  };
}

function assessment(status = "draft"): CsfAssessment {
  return {
    id: "a1",
    service_id: "s1",
    version: 1,
    status,
    approved_at: null,
    approved_by: null,
    answers: [
      answer("ans1", "GV.OC-01", 2, null),
      answer("ans2", "GV.OC-02", 2, null),
    ],
    client_target_tier: 3,
    client_profile: null,
  } as CsfAssessment;
}

interface Held<T> {
  resolve: (v: T) => void;
  reject: (e: unknown) => void;
}
const saves: Array<Held<CsfAnswer> & { answerId: string; patch: object }> = [];

beforeEach(() => {
  saves.length = 0;
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(csfClient.fetchSelfAssessment).mockReset();
  vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(assessment());
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
    (answerId: string, patch: object) =>
      new Promise<CsfAnswer>((resolve, reject) => {
        saves.push({ answerId, patch, resolve, reject });
      }),
  );
  vi.mocked(csfClient.submitSelfAssessment).mockReset();
  vi.mocked(csfClient.submitSelfAssessment).mockResolvedValue(
    assessment("submitted"),
  );
});

async function mount(): Promise<HTMLElement> {
  render(<CsfSelfAssessment serviceId="s1" />);
  return screen.findByRole("button", { name: "Submit for review" });
}

function tierRadio(code: string, tier: number): HTMLElement {
  const group = screen.getByRole("radiogroup", {
    name: `Maturity tier for ${code}`,
  });
  return within(group).getByRole("radio", {
    name: new RegExp(`^T${tier}(?![0-9])`),
  });
}

describe("CsfSelfAssessment through the real questionnaire (#758 review)", () => {
  it("sends no answer save while Submit is in flight: the answer controls are read-only", async () => {
    // Finding 1. Submit cannot START while a save is out, but nothing stopped
    // a save starting while SUBMIT was out: the tier changed during
    // "Submitting…", the PATCH went after the assessment left draft, and its
    // 409 landed after the page became `SelfAssessmentSubmitted`.
    let releaseSubmit: (a: CsfAssessment) => void = () => undefined;
    vi.mocked(csfClient.submitSelfAssessment).mockImplementation(
      () =>
        new Promise<CsfAssessment>((resolve) => {
          releaseSubmit = resolve;
        }),
    );
    const submit = await mount();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(
      screen.getByRole("button", { name: "Submitting…" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-01", 4));
    });
    expect(csfClient.patchSelfAssessmentAnswer).not.toHaveBeenCalled();
    expect(tierRadio("GV.OC-01", 4)).toBeDisabled();
    expect(screen.getByLabelText("Notes for GV.OC-01")).toBeDisabled();

    await act(async () => {
      releaseSubmit(assessment("submitted"));
    });
  });

  it("shows a tier save's failure even after a NEWER notes save of the same row was accepted", async () => {
    // Finding 2. The two fields of one row save separately and the api
    // applies only the fields sent, so a notes save says nothing about the
    // tier. Keyed per row, the accepted notes save made the older tier save
    // "not newest", and its failure was shown nowhere.
    await mount();
    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-01", 4));
    });
    await act(async () => {
      fireEvent.blur(screen.getByLabelText("Notes for GV.OC-01"), {
        target: { value: "  a note  " },
      });
    });
    expect(saves.map((s) => s.patch)).toEqual([
      { maturity_tier: 4 },
      { notes: "a note" },
    ]);

    await act(async () => {
      saves[1].resolve(answer("ans1", "GV.OC-01", 2, "a note"));
    });
    await act(async () => {
      saves[0].reject(SERVER_ERROR());
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("GV.OC-01");
  });

  it("still lets a newer save of the SAME field supersede an older one's failure", async () => {
    await mount();
    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-01", 4));
    });
    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-01", 3));
    });
    expect(saves.map((s) => s.patch)).toEqual([
      { maturity_tier: 4 },
      { maturity_tier: 3 },
    ]);
    await act(async () => {
      saves[1].resolve(answer("ans1", "GV.OC-01", 3, null));
    });
    await act(async () => {
      saves[0].reject(SERVER_ERROR());
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
