// ESLint flat config (ESLint 9). Replaces the legacy .eslintrc.json.
// eslint-config-next 16 ships a native flat-config array at ./core-web-vitals
// that preserves the exact rule set the old `next/core-web-vitals` extends gave
// us (see the commit body for the print-config parity diff). ESLint 10 is
// deliberately deferred: no published Next lint stack runs on v10 yet
// (eslint-plugin-react 7.37.5 calls the removed context.getFilename(), and
// Next's parser trips eslint-scope's missing scopeManager.addGlobals).
const nextCoreWebVitals = require("eslint-config-next/core-web-vitals");

/** @type {import("eslint").Linter.Config[]} */
module.exports = [
  // Flat config has no built-in Next ignores; `next lint` used to add these.
  {
    ignores: [".next/**", "out/**", "build/**", "next-env.d.ts"],
  },
  ...nextCoreWebVitals,
  // REACT-HOOKS v6 ADOPTED (Sprint-5 T9): eslint-config-next 16 bundles
  // eslint-plugin-react-hooks v6, whose 14 React-Compiler-era rules
  // (set-state-in-effect, purity, etc.) were held OFF in Sprint-4 T3 for exact
  // rule parity during the flat-config migration. Sprint-5 T9 adopts all 14 as
  // a deliberate lint tightening: every violation is fixed in source, so no
  // rule is configured off here. The default severities from
  // eslint-config-next/core-web-vitals now stand.
];
