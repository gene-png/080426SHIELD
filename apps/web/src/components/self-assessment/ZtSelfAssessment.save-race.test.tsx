import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * #758, the twin of #252 on the client's ZT self-assessment. Answers save on
 * blur, and Submit did not wait for an answer save still in flight. Submit
 * moves the assessment out of draft, so that save is then refused (409 "Your
 * self-assessment is no longer editable.") -- and by then the page has
 * swapped to `SelfAssessmentSubmitted`, so the refusal lands in a component
 * no longer on screen. The client is told "submitted" while their last answer
 * was lost.
 *
 * Driven through the rendered component, each answer save held open by hand.
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

/** What `lib/zt/client.ts` throws: an error with `status` and `payload`. */
function proxyError(status: number, payload: unknown): Error {
  return Object.assign(new Error(`ZT proxy ${status}`), { status, payload });
}

/** The api's answer PATCH once the assessment is no longer a draft:
 *  `routes/zt.py`, `HTTPException(409, "Your self-assessment is no longer
 *  editable.")`, as `_handle_http_exception` envelopes a string detail. */
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

const CATALOG: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [
        {
          code: "CISA.ID.01",
          pillar_code: "ID",
          name: "Authentication",
          outcome: "Phishing-resistant MFA.",
        },
        {
          code: "CISA.ID.02",
          pillar_code: "ID",
          name: "Identity stores",
          outcome: "One store.",
        },
      ],
    },
  ],
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  total_capabilities: 2,
};

function answer(id: string, code: string, notes: string | null): ZtAnswer {
  return {
    id,
    assessment_id: "a1",
    capability_code: code,
    maturity_stage: 2,
    target_stage: null,
    notes,
    evidence_artifact_id: null,
    locked: false,
    answered_by: null,
    answered_at: null,
  } as ZtAnswer;
}

function assessment(
  status = "draft",
  notes: [string | null, string | null] = [null, null],
): ZtAssessment {
  return {
    id: "a1",
    service_id: "s1",
    framework: "cisa_ztmm_2_0",
    version: 1,
    status,
    approved_at: null,
    approved_by: null,
    answers: [
      answer("ans1", "CISA.ID.01", notes[0]),
      answer("ans2", "CISA.ID.02", notes[1]),
    ],
    client_target_stage: 3,
  } as ZtAssessment;
}

interface Held {
  answerId: string;
  resolve: (a: ZtAnswer) => void;
  reject: (e: unknown) => void;
}
const held: Held[] = [];

beforeEach(() => {
  held.length = 0;
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(ztClient.fetchSelfAssessment).mockReset();
  vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(assessment());
  vi.mocked(ztClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(ztClient.patchSelfAssessmentAnswer).mockImplementation(
    (answerId: string) =>
      new Promise<ZtAnswer>((resolve, reject) => {
        held.push({ answerId, resolve, reject });
      }),
  );
  vi.mocked(ztClient.submitSelfAssessment).mockReset();
  vi.mocked(ztClient.submitSelfAssessment).mockResolvedValue(
    assessment("submitted"),
  );
});

async function mount(): Promise<HTMLElement> {
  render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
  return screen.findByRole("button", { name: "Submit for review" });
}

async function editNotes(code: string, value: string): Promise<void> {
  const box = screen.getByLabelText(`Notes for ${code}`);
  await act(async () => {
    fireEvent.blur(box, { target: { value } });
  });
}

describe("ZtSelfAssessment: Submit and an in-flight answer save (#758)", () => {
  it("tells the client when their last answer is refused after they press Submit", async () => {
    // THE SILENT LOSS. Red on main: Submit went through while the save was
    // out, the page became "submitted", and the 409 had nowhere to show.
    const submit = await mount();
    await editNotes("CISA.ID.01", "the last answer");
    expect(held).toHaveLength(1);

    await act(async () => {
      fireEvent.click(submit);
    });
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("CISA.ID.01");
    expect(alert).toHaveTextContent("no longer editable");
    expect(ztClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("keeps Submit off while a save is out, and on again once it lands", async () => {
    const submit = await mount();
    expect(submit).toBeEnabled();
    await editNotes("CISA.ID.01", "a note");
    expect(submit).toBeDisabled();

    await act(async () => {
      held[0].resolve(answer("ans1", "CISA.ID.01", "a note"));
    });
    expect(submit).toBeEnabled();
  });

  it("stays off until EVERY overlapping save has landed", async () => {
    const submit = await mount();
    await editNotes("CISA.ID.01", "one");
    await editNotes("CISA.ID.02", "two");
    expect(held).toHaveLength(2);

    await act(async () => {
      held[0].resolve(answer("ans1", "CISA.ID.01", "one"));
    });
    expect(submit).toBeDisabled();
    await act(async () => {
      held[1].resolve(answer("ans2", "CISA.ID.02", "two"));
    });
    expect(submit).toBeEnabled();
  });

  it("keeps a refused row's error after ANOTHER row saves, and clears it when that row saves", async () => {
    await mount();
    await editNotes("CISA.ID.01", "refused");
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("CISA.ID.01");

    await editNotes("CISA.ID.02", "fine");
    await act(async () => {
      held[1].resolve(answer("ans2", "CISA.ID.02", "fine"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("CISA.ID.01");

    await editNotes("CISA.ID.01", "accepted now");
    await act(async () => {
      held[2].resolve(answer("ans1", "CISA.ID.01", "accepted now"));
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not let an OLDER save's refusal land over the same row's newer, accepted save", async () => {
    // Two saves of one row; the newer is accepted first, then the older one
    // is refused. The row's state is the newer save's, so nothing is shown.
    await mount();
    await editNotes("CISA.ID.01", "first");
    await editNotes("CISA.ID.01", "second");
    expect(held).toHaveLength(2);
    await act(async () => {
      held[1].resolve(answer("ans1", "CISA.ID.01", "second"));
    });
    await act(async () => {
      held[0].reject(NOT_EDITABLE());
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the outcome is unknown for an unanswered save, and lets Submit through after it", async () => {
    const submit = await mount();
    await editNotes("CISA.ID.01", "maybe saved");
    expect(submit).toBeDisabled();
    await act(async () => {
      held[0].reject(OUTCOME_UNKNOWN());
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "CISA.ID.01: we couldn't confirm whether it was saved.",
    );
    expect(submit).toBeEnabled();
  });
});
