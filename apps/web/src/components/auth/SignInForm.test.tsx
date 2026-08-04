import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignInForm } from "./SignInForm";

// The sign-in form's only side effects are next-auth's client `signIn` and the
// callbackUrl read from the query string. Mock both so the test is offline and
// deterministic and we can drive the exact `signIn` return shape.
vi.mock("next-auth/react", () => ({ signIn: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
}));

import { signIn } from "next-auth/react";

const signInMock = vi.mocked(signIn);

async function submit(): Promise<void> {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "user@atlas.example" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "DemoPass!2026" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("SignInForm — Auth.js v5 credentials signal", () => {
  beforeEach(() => {
    signInMock.mockReset();
  });

  it("reveals the authenticator-code field when signIn returns code=mfa_required", async () => {
    // v5 shape: every credentials failure surfaces error "CredentialsSignin";
    // the MFA branch is distinguished ONLY by the custom `code`. A v4-style
    // check on `error === "mfa_required"` would miss this and fall through to
    // the generic-error branch instead.
    signInMock.mockResolvedValue({
      error: "CredentialsSignin",
      code: "mfa_required",
      status: 401,
      ok: false,
      url: null,
    } as never);

    render(<SignInForm />);
    await submit();

    expect(
      await screen.findByLabelText("Authenticator code"),
    ).toBeInTheDocument();
    // The MFA prompt is not an error state.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(signInMock).toHaveBeenCalledWith(
      "credentials",
      expect.objectContaining({ redirect: false }),
    );
  });

  it("omits the totp key entirely on an empty-code submit", async () => {
    // Real bug found in Sprint 8 T4: passing `totp: totp || undefined` puts a
    // `totp: undefined` key on the signIn options. next-auth's client serializes
    // the body with `new URLSearchParams({...})`, which coerces `undefined` to
    // the literal string "undefined" — a truthy value that defeats authorize's
    // `if (!totp)` guard, so the MFA-required branch tries to verify a bogus code
    // instead of prompting and the authenticator field never appears. The
    // first (code-less) submit must carry NO totp key at all.
    signInMock.mockResolvedValue({
      error: "CredentialsSignin",
      code: "mfa_required",
      status: 401,
      ok: false,
      url: null,
    } as never);

    render(<SignInForm />);
    await submit();

    const secondArg = signInMock.mock.calls[0][1] as object;
    expect(Object.prototype.hasOwnProperty.call(secondArg, "totp")).toBe(false);
  });

  it("shows a generic error (no code field) on a plain credentials failure", async () => {
    // Wrong password: v5 returns error "CredentialsSignin" with the default
    // code "credentials" — must NOT be mistaken for the MFA branch.
    signInMock.mockResolvedValue({
      error: "CredentialsSignin",
      code: "credentials",
      status: 401,
      ok: false,
      url: null,
    } as never);

    render(<SignInForm />);
    await submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid email or password.",
    );
    expect(
      screen.queryByLabelText("Authenticator code"),
    ).not.toBeInTheDocument();
  });
});
