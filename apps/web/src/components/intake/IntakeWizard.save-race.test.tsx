import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as intakeClient from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
  IntakeSubmitRequest,
} from "@/lib/intake/types";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #252: the intake submitted the SERVER's copy of the client's fields, which
 * is refreshed only when a save RETURNS, and nothing stopped a submit while a
 * blur-save was still in flight. The observation spec that found it stored
 * the email-domain fallback as the legal name with every step reporting ok.
 *
 * Driven through the rendered wizard: type into a field, blur it (the save
 * fires and is held open), walk to Review & submit, and read what the Submit
 * button allows and what `submitIntake` is sent.
 */

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { user: { email: "c@example.com" } } }),
}));
vi.mock("@/lib/intake/client", () => ({
  ProxyError: class ProxyError extends Error {},
  fetchIntake: vi.fn(),
  patchIntake: vi.fn(),
  submitIntake: vi.fn(),
}));
vi.mock("@/lib/intake/artifacts", () => ({
  listArtifacts: vi.fn(async () => ({ items: [] })),
}));
vi.mock("./Dropzone", () => ({
  Dropzone: () => null,
  EmptyArtifactsHint: () => null,
}));
vi.mock("./RedactionDisclosure", () => ({ RedactionDisclosure: () => null }));

const patchIntake = vi.mocked(intakeClient.patchIntake);
const submitIntake = vi.mocked(intakeClient.submitIntake);

/** The server's copy before this session's edits: the fallback name. */
function serverState(
  over: Partial<NonNullable<IntakeStateResponse["client"]>> = {},
): IntakeStateResponse {
  return {
    client: {
      id: "client-252",
      legal_name: "engagement-252.example",
      dba_name: null,
      website: null,
      size_band: null,
      industry: null,
      address_line1: null,
      address_line2: null,
      city: null,
      state: null,
      postal_code: null,
      country: null,
      prompting_context: null,
      service_interests: ["tech_debt"],
      intake_completed_at: null,
      ...over,
    },
    service_requests: [],
    intake_completed_at: null,
    contact: null,
  } as IntakeStateResponse;
}

interface Held {
  patch: IntakePatchRequest;
  resolve: (s: IntakeStateResponse) => void;
  reject: (e: unknown) => void;
}

/** Every save is held open until the test settles it. */
const held: Held[] = [];

beforeEach(() => {
  held.length = 0;
  vi.mocked(intakeClient.fetchIntake).mockResolvedValue(serverState());
  patchIntake.mockReset();
  patchIntake.mockImplementation(
    (patch: IntakePatchRequest) =>
      new Promise<IntakeStateResponse>((resolve, reject) => {
        held.push({ patch, resolve, reject });
      }),
  );
  submitIntake.mockReset();
  submitIntake.mockResolvedValue(serverState());
});

/** What `lib/intake/client.ts` throws for an answered refusal. */
function proxyError(status: number, payload: unknown): Error {
  const ProxyError = intakeClient.ProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`Intake proxy ${status}`), {
    status,
    payload,
  });
}

/**
 * The api's schema 422, as `_handle_validation_error` sends it for a value
 * `ClientProfilePatch` refuses. Captured from the api on 2026-10-01 for
 * `{"client": {"website": "example.gov"}}` (`website: HttpUrl`); only the
 * correlation id is dropped.
 */
function schema422(field: string, input: string): Error {
  return proxyError(422, {
    error: {
      code: 422,
      message: "Request validation failed.",
      reason: "schema_url_parsing",
      reasons: ["schema_url_parsing"],
      details: [
        {
          type: "url_parsing",
          loc: ["body", "client", field],
          msg: "Input should be a valid URL, relative URL without a base",
          input,
          ctx: { error: "relative URL without a base" },
        },
      ],
    },
  });
}

/** The proxy's typed 504 (#550): the save may or may not have landed. */
function outcomeUnknown(): Error {
  return proxyError(504, {
    error: {
      code: 504,
      reason: "upstream_outcome_unknown",
      message:
        "We couldn't confirm whether this finished. It may still complete; check before trying again.",
    },
  });
}

async function next(times = 1): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    });
  }
}

/** Type into a step-2 field and blur it, which fires its save. */
async function typeAndBlur(id: string, value: string): Promise<void> {
  const input = document.getElementById(id) as HTMLInputElement;
  expect(input, `no #${id} on this step`).not.toBeNull();
  await act(async () => {
    fireEvent.change(input, { target: { value } });
    fireEvent.blur(input, { target: { value } });
  });
}

/** Mount, open step 2, apply `edits`, and walk on to Review & submit. */
async function editThenReview(
  edits: Array<[string, string]>,
): Promise<HTMLElement> {
  render(<IntakeWizard />);
  await screen.findByRole("button", { name: "Next →" });
  await next(); // -> organization
  for (const [id, value] of edits) await typeAndBlur(id, value);
  await next(4); // -> contact, systems, notes, review
  return screen.findByRole("button", { name: /Submit intake/ });
}

function submitted(): IntakeSubmitRequest {
  expect(submitIntake).toHaveBeenCalledTimes(1);
  return submitIntake.mock.calls[0][0] as IntakeSubmitRequest;
}

describe("IntakeWizard: Submit and an in-flight save (#252)", () => {
  it("keeps Submit off while a save is in flight, and submits the typed legal name once it lands", async () => {
    const submit = await editThenReview([["legal_name", "Atlas Federal LLC"]]);
    expect(held.map((h) => h.patch)).toEqual([
      { client: { legal_name: "Atlas Federal LLC" } },
    ]);

    expect(submit).toBeDisabled();

    await act(async () => {
      held[0].resolve(serverState({ legal_name: "Atlas Federal LLC" }));
    });
    expect(submit).toBeEnabled();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(submitted().client?.legal_name).toBe("Atlas Federal LLC");
  });

  it("stays off until EVERY overlapping save has landed, not just the first", async () => {
    // One boolean that the first completion clears would re-enable Submit
    // here while the second save is still out.
    const submit = await editThenReview([
      ["legal_name", "Atlas Federal LLC"],
      ["city", "Arlington"],
    ]);
    expect(held).toHaveLength(2);
    expect(submit).toBeDisabled();

    await act(async () => {
      held[0].resolve(serverState({ legal_name: "Atlas Federal LLC" }));
    });
    expect(submit).toBeDisabled();
    // And the save indicator does not say "Saved" while one is still out.
    expect(screen.getByText("Saving…")).toBeInTheDocument();

    await act(async () => {
      held[1].resolve(
        serverState({ legal_name: "Atlas Federal LLC", city: "Arlington" }),
      );
    });
    expect(submit).toBeEnabled();
  });

  it("submits what was typed even when the saves' answers land out of order", async () => {
    // Two saves of the same field; the OLDER answer lands last, so the
    // server's copy on this page ends up holding the older value. Submit must
    // send, and the review must show, what was typed last.
    const submit = await editThenReview([
      ["legal_name", "Atlas Federal"],
      ["legal_name", "Atlas Federal LLC"],
    ]);
    expect(held).toHaveLength(2);
    await act(async () => {
      held[1].resolve(serverState({ legal_name: "Atlas Federal LLC" }));
    });
    await act(async () => {
      held[0].resolve(serverState({ legal_name: "Atlas Federal" }));
    });

    expect(screen.getByText("Atlas Federal LLC")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(submitted().client?.legal_name).toBe("Atlas Federal LLC");
  });

  it("drops a value the server REFUSED, keeps the error, and submits what the server holds", async () => {
    // Review of #757, finding 2. A website the schema refuses ("example.gov",
    // `website: HttpUrl`) used to stay in the overlay: the review showed it as
    // accepted and Submit then failed with only "Failed to submit intake."
    const submit = await editThenReview([["website", "example.gov"]]);
    await act(async () => {
      held[0].reject(schema422("website", "example.gov"));
    });

    expect(screen.getByText(/^Couldn.t save:/)).toBeInTheDocument();
    expect(screen.queryByText("example.gov")).not.toBeInTheDocument();
    expect(submit).toBeEnabled();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(submitted().client?.website).toBeUndefined();
  });

  it("keeps a refused field's error after ANOTHER field saves, and clears it when that field saves", async () => {
    // Review of #757, finding 4: a later answer overwrote an earlier save's
    // error, which is what made the refusals above silent.
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(); // -> organization
    await typeAndBlur("website", "example.gov");
    await act(async () => {
      held[0].reject(schema422("website", "example.gov"));
    });
    expect(screen.getByText(/^Couldn.t save:/)).toBeInTheDocument();

    await typeAndBlur("city", "Arlington");
    await act(async () => {
      held[1].resolve(serverState({ city: "Arlington" }));
    });
    expect(screen.getByText(/^Couldn.t save:/)).toBeInTheDocument();

    await typeAndBlur("website", "https://atlas.example");
    await act(async () => {
      held[2].resolve(
        serverState({ city: "Arlington", website: "https://atlas.example/" }),
      );
    });
    expect(screen.queryByText(/^Couldn.t save:/)).not.toBeInTheDocument();
  });

  it("submits exactly the client fields onSubmit sends, and never lays a contact override over the server's", async () => {
    // Review of #757, finding 1. Step 3's contact override is saved through
    // `client` but NOT sent at submit, so laying it over the server's copy
    // showed a failed override on revisit as if it were stored.
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(2); // -> contact
    await act(async () => {
      fireEvent.click(
        screen.getByRole("checkbox", {
          name: /I am not the primary contact/,
        }),
      );
    });
    const name = document.getElementById(
      "primary_contact_name",
    ) as HTMLInputElement;
    expect(name, "setup: the override fields must open").not.toBeNull();
    await act(async () => {
      fireEvent.change(name, { target: { value: "Pat Doe" } });
      fireEvent.blur(name, { target: { value: "Pat Doe" } });
    });
    expect(held.map((h) => h.patch)).toEqual([
      { client: { primary_contact_name: "Pat Doe" } },
    ]);
    // Its answer never arrives: the case where an overlay keeps the typed
    // value for fields Submit sends.
    await act(async () => {
      held[0].reject(outcomeUnknown());
    });

    await next(); // -> systems
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "← Back" }));
    });
    expect(
      document.getElementById("primary_contact_name"),
      "the override reappeared from the page's own memory, not the server",
    ).toBeNull();
    expect(
      screen.getByRole("checkbox", { name: /I am not the primary contact/ }),
    ).not.toBeChecked();

    await next(3); // -> review
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Submit intake/ }));
    });
    // The fields onSubmit sends, as derived from main's onSubmit (#252).
    expect(Object.keys(submitted().client ?? {}).sort()).toEqual(
      [
        "address_line1",
        "address_line2",
        "city",
        "country",
        "dba_name",
        "industry",
        "legal_name",
        "postal_code",
        "prompting_context",
        "service_interests",
        "size_band",
        "state",
        "website",
      ].sort(),
    );
  });

  it("after a save whose outcome is unknown (#550), says so and submits the typed value, never the server's older one", async () => {
    const submit = await editThenReview([["legal_name", "Atlas Federal LLC"]]);
    const ProxyError = intakeClient.ProxyError as unknown as new (
      m: string,
    ) => Error;
    await act(async () => {
      held[0].reject(
        Object.assign(new ProxyError("Intake proxy 504"), {
          status: 504,
          payload: {
            error: {
              code: 504,
              reason: "upstream_outcome_unknown",
              message:
                "We couldn't confirm whether this finished. It may still complete; check before trying again.",
            },
          },
        }),
      );
    });

    expect(
      screen.getByText(
        /Couldn.t save: We couldn.t confirm whether this finished/,
      ),
    ).toBeInTheDocument();
    // The review shows the value that will be sent, which is the typed one.
    expect(screen.getByText("Atlas Federal LLC")).toBeInTheDocument();
    expect(
      screen.queryByText("engagement-252.example"),
    ).not.toBeInTheDocument();
    expect(submit).toBeEnabled();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(submitted().client?.legal_name).toBe("Atlas Federal LLC");
  });

  it("keeps Submit off while a services save is in flight, and submits the typed picks", async () => {
    // `service_interests` is read by onSubmit too, and saved from step 1.
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    const checkbox = await screen.findByRole("checkbox", {
      name: /ATT&CK/i,
    });
    await act(async () => {
      fireEvent.click(checkbox);
    });
    expect(held).toHaveLength(1);
    expect(held[0].patch.client?.service_interests).toEqual(
      expect.arrayContaining(["tech_debt", "attack_coverage"]),
    );
    await next(5);
    const submit = await screen.findByRole("button", { name: /Submit intake/ });
    expect(submit).toBeDisabled();

    await act(async () => {
      held[0].resolve(serverState());
    });
    expect(submit).toBeEnabled();
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(submitted().client?.service_interests).toEqual(
      expect.arrayContaining(["tech_debt", "attack_coverage"]),
    );
  });
});
