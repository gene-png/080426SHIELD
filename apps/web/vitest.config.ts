import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Minimal web unit-test harness (Sprint 5 T8). jsdom + testing-library, no
// snapshots, no coverage thresholds. Tests MUST be deterministic and offline:
// fetch is mocked per test (see vitest.setup.ts), never hitting the network.
const srcDir = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig({
  // esbuild handles the JSX transform; force the automatic runtime so component
  // files need no explicit React import (tsconfig uses jsx: "preserve", which
  // esbuild cannot execute directly).
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    // Mirror tsconfig's "@/*" -> src path alias. Anchored to "@/" so it never
    // swallows scoped package names like "@shield/design-system".
    alias: [{ find: /^@\//, replacement: `${srcDir}/` }],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Every test starts from a clean mock slate.
    clearMocks: true,
    restoreMocks: true,
  },
});
