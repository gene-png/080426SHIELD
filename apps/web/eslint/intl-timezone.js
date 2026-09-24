// Every `Intl.DateTimeFormat` in product code names its time zone.
//
// A formatter without `timeZone` formats in the VIEWER's zone. The released
// date on the client dashboards is an instant, and at 02:00 UTC it read as the
// day before for anyone west of UTC -- one release, different days for
// different readers, and a different day from the UTC the API stores. The
// shared badge was pinned to UTC; ATT&CK carried a private copy that was not.
//
// A RULE OVER EVERY FILE, not a check of one: a gate scoped to the shared
// formatter would have been green through both reports. It matches the
// LITERAL spellings `Intl.DateTimeFormat(...)` and `new Intl.DateTimeFormat(...)`,
// which is how every product call site is written. Known escapes, none in the
// tree when this was written: an alias (`const { DateTimeFormat } = Intl`),
// `globalThis.Intl` / `window.Intl`, a computed member (`Intl["DateTimeFormat"]`),
// a `timeZone` key anywhere else in the call's arguments, and
// `timeZone: undefined`. And by reach: the rule runs on
// `apps/web/src/**/*.{ts,tsx}` only, so a `.js` file there, or
// `packages/design-system` (which has no lint script), is not checked. Tests
// are exempt (see `eslint.config.js`).
//
// Fails closed on options it cannot see into (a variable, a spread): a zone it
// cannot SEE is a zone it cannot vouch for. Write the object literal, or
// disable the line with a reason.
//
// Out of scope, stated so nobody reads more into it: `toLocaleString` /
// `toLocaleDateString` / `toLocaleTimeString` also format in the viewer's zone,
// and `toLocaleString` is shared with numbers, so a syntax rule cannot tell a
// date from a price there.

const MESSAGE =
  "Intl.DateTimeFormat must name its zone: pass an options object literal " +
  'with `timeZone` (e.g. `timeZone: "UTC"`). Without one it formats in the ' +
  "viewer's zone, and one instant can read as different days to different readers.";

const NO_ZONE = ":not(:has(ObjectExpression > Property[key.name='timeZone']))";

module.exports = {
  rules: {
    "no-restricted-syntax": [
      "error",
      {
        selector: `NewExpression[callee.object.name='Intl'][callee.property.name='DateTimeFormat']${NO_ZONE}`,
        message: MESSAGE,
      },
      {
        selector: `CallExpression[callee.object.name='Intl'][callee.property.name='DateTimeFormat']${NO_ZONE}`,
        message: MESSAGE,
      },
    ],
  },
};
