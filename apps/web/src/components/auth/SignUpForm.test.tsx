import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
});
