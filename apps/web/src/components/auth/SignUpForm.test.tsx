import "@testing-library/jest-dom/vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignUpForm } from "./SignUpForm";

// SignUpForm's side effects: POST /api/proxy/auth/register (fetch), the
// next-auth client `signIn` on success, and a full-page nav to /intake. Mock
// all three so the test is offline and deterministic.
vi.mock("next-auth/react", () => ({ signIn: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

import { signIn } from "next-auth/react";

const signInMock = vi.mocked(signIn);
const fetchMock = vi.fn();
const assignMock = vi.fn();

function fill(): void {
  fireEvent.change(screen.getByLabelText("Full name"), {
    target: { value: "Gene" },
  });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "gene@acme.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "correct horse battery staple!" },
  });
}

function clickCreate(): void {
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
}

describe("SignUpForm — open self-registration (D-034)", () => {
  beforeEach(() => {
    signInMock.mockReset();
    fetchMock.mockReset();
    assignMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign: assignMock },
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders name, email, and password fields", () => {
    render(<SignUpForm />);
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("posts to the register proxy, signs in, and navigates to /intake on success", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 201 });
    signInMock.mockResolvedValue({ ok: true, error: null } as never);

    render(<SignUpForm />);
    fill();
    clickCreate();

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/proxy/auth/register",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(signInMock).toHaveBeenCalledWith(
        "credentials",
        expect.objectContaining({ email: "gene@acme.com", redirect: false }),
      ),
    );
    await waitFor(() => expect(assignMock).toHaveBeenCalledWith("/intake"));
  });

  it("re-enables Create account when the error body is not JSON (#389)", async () => {
    /**
     * The submit handler read `await res.json()` unguarded inside the typed
     * branch. A non-JSON body -- a proxy HTML page, an empty 429, a gateway
     * timeout -- threw, the handler's promise rejected, and `setPending(false)`
     * never ran: the button stayed disabled forever with nothing on screen, on
     * the PUBLIC sign-up page, and the user could not retry without reloading.
     *
     * RED ON REVERT: remove the try/catch around the parse and this hangs --
     * the button stays disabled and the copy never appears.
     */
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON at position 0");
      },
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    // Something is said...
    expect(
      await screen.findByText(/double-check your name/i),
    ).toBeInTheDocument();
    // ...and the user can try again, which is the half that was broken.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /create account/i }),
      ).toBeEnabled(),
    );
    expect(signInMock).not.toHaveBeenCalled();
  });

  it("shows friendly copy on the email field for a duplicate email and never signs in", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: { reason: "email_exists" } }),
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    expect(
      await screen.findByText(/an account already exists/i),
    ).toBeInTheDocument();
    expect(signInMock).not.toHaveBeenCalled();
  });

  it("renders the server's rate-limit copy instead of telling the user to retry now", async () => {
    // THE DEFECT THIS TEST EXISTS FOR, and it was certified as impossible.
    //
    // `dashboards-render-the-typed-reason.test.ts` exempted this component
    // because "every typed reason /auth/register can emit is a 409 or 422".
    // `register` opens with `limiter.enforce_auth(...)`, which raises a typed
    // 429 before the handler body runs -- so a throttled sign-up fell past the
    // status gate to the untyped fallback, "Something went wrong creating your
    // account. Try again.", and trying again re-trips the limiter.
    //
    // Both halves are asserted: the server's sentence appears, and the advice
    // that re-trips the limiter does not. Pinning only the first would let a
    // future change render both.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({
        error: {
          reason: "rate_limited",
          message: "Too many requests. Please slow down and try again shortly.",
        },
      }),
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    expect(
      await screen.findByText(/slow down and try again shortly/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/something went wrong creating your account/i),
    ).toBeNull();
    expect(signInMock).not.toHaveBeenCalled();

    // WHERE it renders, which is the branch's whole reason for existing and
    // was pinned by nothing. Measured: replace `reason === "rate_limited"`
    // with an unreachable code and the assertions above STAY GREEN -- the
    // message falls through to `carriesUserFacingCopy` and renders on the
    // EMAIL FIELD, where `findByText` finds it just as happily. Only the
    // message-less test below went red, and that is about the fallback, not
    // about placement.
    //
    // So a later simplification that deletes this branch as redundant would
    // reinstate exactly the false claim its comment warns against, against a
    // green suite. Two discriminators, because the form error is the only
    // `role="alert"` and a field error is the only thing that marks an input
    // invalid.
    expect(
      within(screen.getByRole("alert")).getByText(
        /slow down and try again shortly/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
  });

  it("falls back to its own copy when a 429 carries no usable message", async () => {
    // Missing data defaults to UNCONFIRMED: an untyped or message-less 429 is
    // still a throttle, and the user must not be told to retry immediately.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ error: { reason: "rate_limited" } }),
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    expect(
      await screen.findByText(/wait a moment before trying again/i),
    ).toBeInTheDocument();
  });

  it("shows the server message on the password field for a weak password", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        error: { reason: "password_policy", message: "Password too weak." },
      }),
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    expect(await screen.findByText("Password too weak.")).toBeInTheDocument();
    expect(signInMock).not.toHaveBeenCalled();
  });

  // #317. #307 gave every schema-level 422 a typed `reason`, and the component
  // chose between typed copy and the friendly fallback by testing that field's
  // PRESENCE — so the fallback became unreachable and "Request validation
  // failed." rendered under the Email field on the public sign-up page.
  //
  // The reason codes below are written out as literals rather than imported
  // from the component or from any shared constant. A test that derives its
  // expected value from the thing it is pinning agrees with it by construction
  // and cannot fail (#72); these are copied from `schema_reasons()` in
  // `apps/api/app/exceptions.py`, which is the surface that produces them.
  const schemaReasonFallback = "schema_string_too_short";
  const schemaReasonMixed = "schema_multiple";

  it.each([
    ["a single failing field", schemaReasonFallback],
    ["several failing fields at once", schemaReasonMixed],
  ])(
    "falls back to the friendly prompt for a schema 422 with %s",
    async (_label, reason) => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: { reason, message: "Request validation failed." },
        }),
      });

      render(<SignUpForm />);
      fill();
      clickCreate();

      // Assert what must APPEAR before what must not: an absence checked while
      // the handler is still resolving passes vacuously.
      expect(
        await screen.findByText(/please double-check your name, email/i),
      ).toBeInTheDocument();
      expect(screen.queryByText(/request validation failed/i)).toBeNull();
      expect(signInMock).not.toHaveBeenCalled();
    },
  );

  // The other half of the same branch, and it is what keeps the fix honest: a
  // "repair" that simply deleted the typed-reason branch would satisfy the two
  // cases above and silently discard every friendly message the API does send.
  it("still surfaces a typed non-schema rejection's own copy on the email field", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        error: {
          reason: "email_domain_unavailable",
          message: "That domain cannot be used for self-registration.",
        },
      }),
    });

    render(<SignUpForm />);
    fill();
    clickCreate();

    expect(
      await screen.findByText(
        "That domain cannot be used for self-registration.",
      ),
    ).toBeInTheDocument();
    expect(signInMock).not.toHaveBeenCalled();
  });
});
