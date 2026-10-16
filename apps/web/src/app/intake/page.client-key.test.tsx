import { describe, expect, it, vi } from "vitest";

import IntakePage from "./page";

/**
 * #1262, the `/intake` residual (review of 69fbc5b1, finding 1). The wizard
 * pins the client it loaded, so switching client in the header must give a
 * NEW wizard: the switcher sets the cookie and calls `router.refresh()`,
 * which keeps client component state. The page keys the wizard on the active
 * client, so the refresh remounts it and it loads the new client.
 */

const cookie = { value: undefined as string | undefined };
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) =>
      name === "shield_active_client_id" && cookie.value
        ? { value: cookie.value }
        : undefined,
  })),
}));
vi.mock("@/components/intake/IntakeWizard", () => ({
  IntakeWizard: () => null,
}));

describe("IntakePage keys the wizard on the active client (#1262)", () => {
  it("gives a different key for each active client", async () => {
    cookie.value = "00000000-0000-4000-8000-0000000000a1";
    const a = await IntakePage();
    cookie.value = "00000000-0000-4000-8000-0000000000b2";
    const b = await IntakePage();
    expect(a.key).toBe("00000000-0000-4000-8000-0000000000a1");
    expect(b.key).toBe("00000000-0000-4000-8000-0000000000b2");
  });

  it("still renders the wizard with no active client (a client-role user)", async () => {
    cookie.value = undefined;
    const el = await IntakePage();
    expect(el).not.toBeNull();
  });
});
