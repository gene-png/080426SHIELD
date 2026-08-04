import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Unmount rendered trees between tests so mount effects don't bleed across
// cases.
afterEach(() => {
  cleanup();
});

// FAIL LOUDLY on accidental real network: the harness must be deterministic and
// offline. Any test that reaches component code doing an unmocked fetch trips
// this instead of silently hanging or hitting a real host. Tests that exercise
// fetch mock it explicitly (vi.mock the lib client, or override this stub).
if (typeof globalThis.fetch === "undefined") {
  globalThis.fetch = vi.fn(() => {
    throw new Error(
      "Unmocked fetch in a unit test — mock the network explicitly.",
    );
  }) as unknown as typeof fetch;
}
