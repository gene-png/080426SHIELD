/**
 * #1120 "Start a revision": the web copy, approved verbatim by the advisor
 * (#736 6136101129, item 6). Extracted by script from section 8 of the #1120
 * design note rev 10 (sha256 c5fcfb745c6c4ad9...), never retyped; do not edit
 * by hand. Placeholders: {v} the version revised, {v+1} the new one, {n} a
 * count, {codes} / {code} technique codes, {name} / {date} / {reason} the
 * revision's provenance (`revision` on the assessment response).
 */
export const REVISION_COPY = {
  V1: "Start a revision",
  V2: "Start a revision of version {v}?",
  V2a: "This creates version {v+1} as a draft, with every answer, score, note and consultant edit copied from version {v}. Version {v} and its reports are not changed, and the client sees nothing new until a report from version {v+1} is released.",
  V2b_LABEL: "What is this revision for?",
  V2b_HINT: "Required. Saved in the audit log with your name and the time.",
  V2c_CONFIRM: "Start revision",
  V2c_CANCEL: "Cancel",
  V3: "This revision uses the current scoring rules. Version {v} was approved under earlier rules, so some results may differ from what the client has.",
  V4: "This revision uses the current ATT&CK catalog. {n} techniques from version {v} are no longer in it and were not copied: {codes}.",
  V4_ONE:
    "1 technique from version {v} is no longer in it and was not copied: {code}.",
  V5: "Revision of version {v}, started by {name} on {date}: {reason}.",
} as const;
