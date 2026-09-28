import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignUpForm } from "./SignUpForm";

// #727, D-104: `/auth/register` refuses an email whose domain maps to an
// archived client with a typed 409, reason `client_archived`. 409 rather than
// 403 because this form reads a typed body only for 409, 422 and 429; a 403
// would reach the "Something went wrong" fallback and drop the message.
vi.mock("next-auth/react", () => ({ signIn: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

import { signIn } from "next-auth/react";

const signInMock = vi.mocked(signIn);
const fetchMock = vi.fn();

describe("SignUpForm: a domain that leads to an archived client", () => {
  beforeEach(() => {
    signInMock.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the API's archived copy and does not sign in", async () => {
    const copy =
      "Your organization's SHIELD account has been archived, so it is no longer available.";
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        error: { reason: "client_archived", message: copy },
      }),
    });

    render(<SignUpForm />);
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Coworker" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "coworker@atlas.example" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery staple!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(copy)).toBeInTheDocument();
    expect(signInMock).not.toHaveBeenCalled();
  });
});
