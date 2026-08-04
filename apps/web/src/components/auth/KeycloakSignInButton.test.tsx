import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KeycloakSignInButton } from "./KeycloakSignInButton";

// The button's only side effect is next-auth's client `signIn`. Mock it so the
// test is offline and we can assert the exact provider + options it is called
// with.
vi.mock("next-auth/react", () => ({ signIn: vi.fn() }));

import { signIn } from "next-auth/react";

const signInMock = vi.mocked(signIn);

describe("KeycloakSignInButton", () => {
  beforeEach(() => {
    signInMock.mockReset();
  });

  it("renders the Keycloak sign-in button", () => {
    render(<KeycloakSignInButton />);
    expect(
      screen.getByRole("button", { name: "Sign in with Keycloak" }),
    ).toBeInTheDocument();
  });

  it('calls signIn("keycloak", { callbackUrl: "/" }) on click', () => {
    render(<KeycloakSignInButton />);
    fireEvent.click(
      screen.getByRole("button", { name: "Sign in with Keycloak" }),
    );
    expect(signInMock).toHaveBeenCalledWith("keycloak", { callbackUrl: "/" });
  });
});
