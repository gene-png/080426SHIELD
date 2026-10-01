import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #758 on the client's CSF self-assessment: the twin of the ZT file beside
 * this one, and of #252. Submit did not wait for an answer save still in
 * flight; it moves the assessment out of draft, the save is then refused
 * (409 "Your self-assessment is no longer editable."), and the page has
 * already become `SelfAssessmentSubmitted`, so the client is never told.
 *
 * Driven through the rendered component. The questionnaire is stood in for
 * by a control per answer that blurs a note into `onAnswerUpdate`, exactly
 * the call the real `CsfQuestionnaire` makes; each save is held open by hand.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));
vi.mock("@/components/admin/csf/CsfQuestionnaire", () => ({
  CsfQuestionnaire: ({
    onAnswerUpdate,
  }: {
    onAnswerUpdate: (id: string, patch: { notes: string }) => void;
  }) => (
    <div>
      {[
        ["ans1", "GV.OC-01"],
        ["ans2", "GV.OC-02"],
      ].map(([id, code]) => (
        <textarea
          key={id}
          aria-label={`Notes for ${code}`}
          onBlur={(e) => onAnswerUpdate(id, { notes: e.currentTarget.value })}
        />
      ))}
    </div>
  ),
}));

/** What `lib/csf/client.ts` throws: an error with `status` and `payload`. */
function proxyError(status: number, payload: unknown): Error {
  return Object.assign(new Error(`CSF proxy ${status}`), { status, payload });
}

/** `routes/csf.py`'s answer PATCH once the assessment is not a draft:
 *  `HTTPException(409, "Your self-assessment is no longer editable.")`. */
const NOT_EDITABLE = () =>
  proxyError(409, {
    error: {
      code: 409,
      message: "Your self-assessment is no longer editable.",
    },
  });

const OUTCOME_UNKNOWN = () =>
  proxyError(504, {
    error: {
      code: 504,
      reason: "upstream_outcome_unknown",
      message:
        "We couldn't confirm whether this finished. It may still complete; check before trying again.",
    },
  });

const CATALOG = {
  functions: [],
  tiers: [
    { tier: 1, short_label: "Partial", description: "" },
    { tier: 2, short_label: "Risk Informed", description: "" },
    { tier: 3, short_label: "Repeatable", description: "" },
    { tier: 4, short_label: "Adaptive", description: "" },
  ],
  total_subcategories: 2,
} as unknown as CsfCatalog;

function answer(id: string, code: string, notes: string | null): CsfAnswer {
  return {
    id,
    assessment_id: "a1",
    subcategory_code: code,
    maturity_tier: 2,
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
      answer("ans1", "GV.OC-01", null),
      answer("ans2", "GV.OC-02", null),
    ],
    client_target_tier: 3,
    client_profile: null,
  } as CsfAssessment;
}

interface Held {
  answerId: string;
  resolve: (a: CsfAnswer) => void;
  reject: (e: unknown) => void;
}
const held: Held[] = [];

beforeEach(() => {
  held.length = 0;
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(csfClient.fetchSelfAssessment).mockReset();
  vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(assessment());
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
    (answerId: string) =>
      new Promise<CsfAnswer>((resolve, reject) => {
        held.push({ answerId, resolve, reject });
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

async function editNotes(code: string, value: string): Promise<void> {
  const box = screen.getByLabelText(`Notes for ${code}`);
  await act(async () => {
    fireEvent.blur(box, { target: { value } });
  });
}

describe("CsfSelfAssessment: Submit and an in-flight answer save (#758)", () => {
  it("tells the client when their last answer is refused after they press Submit", async () => {
    // THE SILENT LOSS. Red on main: Submit went through while the save was
    // out, the page became "submitted", and the 409 had nowhere to show.
    const submit = await mount();
    await editNotes("GV.OC-01", "the last answer");
    expect(held).toHaveLength(1);

    await act(async () => {
      fireEvent.click(submit);
    });
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("GV.OC-01");
    expect(alert).toHaveTextContent("no longer editable");
    expect(csfClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("keeps Submit off while a save is out, and on again once it lands", async () => {
    const submit = await mount();
    expect(submit).toBeEnabled();
    await editNotes("GV.OC-01", "a note");
    expect(submit).toBeDisabled();

    await act(async () => {
      held[0].resolve(answer("ans1", "GV.OC-01", "a note"));
    });
    expect(submit).toBeEnabled();
  });

  it("stays off until EVERY overlapping save has landed", async () => {
    const submit = await mount();
    await editNotes("GV.OC-01", "one");
    await editNotes("GV.OC-02", "two");
    expect(held).toHaveLength(2);

    await act(async () => {
      held[0].resolve(answer("ans1", "GV.OC-01", "one"));
    });
    expect(submit).toBeDisabled();
    await act(async () => {
      held[1].resolve(answer("ans2", "GV.OC-02", "two"));
    });
    expect(submit).toBeEnabled();
  });

  it("keeps a refused row's error after ANOTHER row saves, and clears it when that row saves", async () => {
    await mount();
    await editNotes("GV.OC-01", "refused");
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("GV.OC-01");

    await editNotes("GV.OC-02", "fine");
    await act(async () => {
      held[1].resolve(answer("ans2", "GV.OC-02", "fine"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("GV.OC-01");

    await editNotes("GV.OC-01", "accepted now");
    await act(async () => {
      held[2].resolve(answer("ans1", "GV.OC-01", "accepted now"));
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not let an OLDER save's refusal land over the same row's newer, accepted save", async () => {
    // Two saves of one row; the newer is accepted first, then the older one
    // is refused. The row's state is the newer save's, so nothing is shown.
    await mount();
    await editNotes("GV.OC-01", "first");
    await editNotes("GV.OC-01", "second");
    expect(held).toHaveLength(2);
    await act(async () => {
      held[1].resolve(answer("ans1", "GV.OC-01", "second"));
    });
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the outcome is unknown for an unanswered save, and lets Submit through after it", async () => {
    const submit = await mount();
    await editNotes("GV.OC-01", "maybe saved");
    expect(submit).toBeDisabled();
    await act(async () => {
      held[0].reject(OUTCOME_UNKNOWN());
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "GV.OC-01: we couldn't confirm whether it was saved.",
    );
    expect(submit).toBeEnabled();
  });
});
