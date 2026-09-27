import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignInForm } from "./SignInForm";

// #727, D-104: the API refuses a user of an archived client with a typed 403,
// reason `client_archived`, at password login and at the MFA step. `authorize`
// carries any typed 403 reason to the form as `result.code`; this pins that the
// form explains it rather than claiming the password was wrong.
vi.mock("next-auth/react", () => ({ signIn: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
}));

import { signIn } from "next-auth/react";

const signInMock = vi.mocked(signIn);

describe("SignInForm: a user of an archived client", () => {
  beforeEach(() => {
    signInMock.mockReset();
  });

  it("says the organization is archived, not that the password is wrong", async () => {
    signInMock.mockResolvedValue({
      error: "CredentialsSignin",
      code: "client_archived",
      status: 401,
      ok: false,
      url: null,
    } as never);

    render(<SignInForm />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@atlas.example" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "DemoPass!2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Your organization's SHIELD account has been archived",
    );
    expect(alert).not.toHaveTextContent("Invalid email or password.");
  });
});
