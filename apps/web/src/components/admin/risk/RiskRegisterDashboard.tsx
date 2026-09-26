"use client";
import * as React from "react";
import Link from "next/link";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  DataTable,
  EmptyState,
  NumberCard,
  type DataTableColumn,
} from "@shield/design-system";

import {
  describeRiskError,
  exportRiskRegister,
  fetchRiskGate,
  fetchRiskRegisterLatest,
  generateRiskRegister,
  getActiveClientId,
  getClientName,
} from "@/lib/risk/client";
import {
  IMPACTS,
  LIKELIHOODS,
  TIER_COLOR,
  isImpact,
  isLikelihood,
  tierFor,
  titleCase,
  type RiskTier,
} from "@/lib/risk/matrix";
import { RunAiGuard } from "@/components/admin/RunAiGuard";

import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import type { JSX } from "react";

/**
 * #403. Service tokens as the API spells them, for the scored-coverage banner.
 *
 * `?? s.service` at the call site rather than a lookup that can return
 * undefined: a service added on the API side must render as its raw token —
 * which is ugly and legible — instead of vanishing from a disclosure or
 * printing "undefined" beside a real count. A missing label is a cosmetic
 * defect; a missing ROW is the disclosure failing silently, which is the
 * failure this banner exists to prevent.
 *
 * DUPLICATED, unavoidably: `_SERVICE_LABELS` in `app/risk/exporters.py` holds
 * the same three strings for the client's deliverable. No shared label map
 * exists in this repo to reuse, and a Python dict cannot be shared with TSX, so
 * this is a synchronization whose window is named rather than a derivation.
 * Change both, or the client's PDF and this screen disagree about which
 * assessment a count belongs to.
 */
const SERVICE_LABELS: Record<string, string> = {
  attack: "ATT&CK coverage",
  csf: "NIST CSF",
  zt: "Zero Trust",
};

function TierChip({ tier }: { tier: string | null }): JSX.Element {
  const t = (tier ?? "negligible") as RiskTier;
  const color = TIER_COLOR[t] ?? TIER_COLOR.negligible;
  return (
    <span
      className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ backgroundColor: color.bg, color: color.fg }}
    >
      {titleCase(tier)}
    </span>
  );
}

function Matrix({ entries }: { entries: RiskEntry[] }): JSX.Element {
  const counts = new Map<string, number>();
  for (const e of entries) {
    if (isLikelihood(e.likelihood) && isImpact(e.impact)) {
      const key = `${e.likelihood}|${e.impact}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  const rows = [...LIKELIHOODS].reverse();
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-center text-xs">
        <thead>
          <tr>
            <th className="p-2" />
            {IMPACTS.map((im) => (
              <th key={im} className="p-2 font-medium text-ink-secondary">
                {titleCase(im)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((lk) => (
            <tr key={lk}>
              <th
                scope="row"
                className="whitespace-nowrap p-2 text-right font-medium text-ink-secondary"
              >
                {titleCase(lk)}
              </th>
              {IMPACTS.map((im) => {
                const color = TIER_COLOR[tierFor(lk, im)];
                const n = counts.get(`${lk}|${im}`) ?? 0;
                return (
                  <td
                    key={im}
                    className="h-12 w-16 border border-white text-sm font-semibold"
                    style={{ backgroundColor: color.bg, color: color.fg }}
                    title={`${titleCase(lk)} × ${titleCase(im)}`}
                  >
                    {n > 0 ? n : ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const COLUMNS: DataTableColumn<RiskEntry>[] = [
  { key: "title", header: "Weakness", cell: (r) => r.title },
  { key: "axis", header: "Axis", cell: (r) => titleCase(r.axis) },
  {
    key: "li",
    header: "Likelihood × Impact",
    cell: (r) => `${titleCase(r.likelihood)} × ${titleCase(r.impact)}`,
  },
  { key: "tier", header: "Tier", cell: (r) => <TierChip tier={r.tier} /> },
  {
    key: "action",
    header: "Recommended",
    cell: (r) => titleCase(r.recommended_action),
  },
  {
    key: "source",
    header: "Source",
    // #132 review. `r.source_id ?? "—"` made a DROPPED source identical to an
    // absent one -- this issue's own harm, in the field the same PR newly
    // started validating. The unlinked banner deliberately excludes source_id
    // (a dropped source changes no linkage the consultant sees on the row), so
    // without this the drop reached no surface at all.
    cell: (r) => {
      const dropped = r.dropped_links?.source_id ?? [];
      if (r.source_id) return r.source_id;
      if (dropped.length > 0) {
        return (
          <span
            className="text-status-warning-fg"
            title={`The model sent ${dropped.map((d) => `"${d}"`).join(", ")}, which names no finding in this client's assessments, so it was not stored.`}
            data-testid="risk-source-dropped"
          >
            not recognised
          </span>
        );
      }
      return "—";
    },
  },
];

function DownloadLink({
  id,
  filename,
  label,
}: {
  id: string | null;
  filename: string | null;
  label: string;
}): JSX.Element | null {
  if (!id) return null;
  return (
    <a
      href={`/api/proxy/artifacts/${id}/download`}
      className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink-primary hover:bg-surface-sunken"
    >
      {label}
      {filename ? (
        <span className="ml-1 text-ink-tertiary">({filename})</span>
      ) : null}
    </a>
  );
}

export function RiskRegisterDashboard(): JSX.Element {
  const [cid, setCid] = React.useState<string | null>(null);
  const [clientName, setClientName] = React.useState("Client");
  const [gate, setGate] = React.useState<RiskGate | null>(null);
  const [register, setRegister] = React.useState<RiskRegister | null>(null);
  // #244: DERIVED from `register`, not held beside it.
  //
  // This was separate state, and the reason was real at the time: `export`
  // returned `_serialize(db, reg)` with no `excluded_inputs`, the schema
  // defaulted it to `[]`, and `setRegister(await exportRiskRegister(cid))`
  // therefore erased the disclosure at the exact moment the consultant did the
  // thing it warns about. The workaround was to keep a copy no later response
  // could clear.
  //
  // `_serialize` now reads the set back from the persisted snapshot on EVERY
  // path, so every response carries the same value and there is nothing left
  // to keep in sync. `CLAUDE.md` prefers a derivation over a synchronization
  // for exactly this reason: a derived value cannot be out of sync, whereas a
  // synchronized one merely is not, right now, for reasons that have to keep
  // holding -- and one of those reasons had already stopped holding.
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState<"generate" | "export" | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    (async () => {
      try {
        const id = await getActiveClientId();
        if (!active) return;
        setCid(id);
        if (!id) {
          setLoading(false);
          return;
        }
        const [name, g, reg] = await Promise.all([
          getClientName(id),
          fetchRiskGate(id),
          fetchRiskRegisterLatest(id),
        ]);
        if (!active) return;
        setClientName(name);
        setGate(g);
        setRegister(reg);
      } catch (err) {
        if (active) setError(describeRiskError(err));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function onGenerate(): Promise<void> {
    if (!cid) return;
    setBusy("generate");
    setError(null);
    try {
      const reg = await generateRiskRegister(cid);
      setRegister(reg);
    } catch (err) {
      setError(describeRiskError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onExport(): Promise<void> {
    if (!cid) return;
    setBusy("export");
    setError(null);
    try {
      // Safe to assign wholesale -- and this comment is now load-bearing for
      // TWO disclosures, which is why it says so explicitly.
      //
      // The export response carries the same persisted withheld set as every
      // other path (#244); before that it carried `[]` and this line was the
      // one that erased the banner. #372's batch tally was ABOUT TO REPEAT
      // that exactly: it shipped response-only, so `export` returned the
      // schema default and this line destroyed the "INCOMPLETE" warning at the
      // moment the consultant did the thing it warns against.
      //
      // It is persisted now too, in the same provenance column, so both
      // survive. **Anything added to this response that is not persisted
      // breaks this line again** -- the sentence "safe to assign wholesale" is
      // a claim about every field, and it expires silently the next time one
      // is added. That is the precondition-comment shape CLAUDE.md records,
      // and it has now caught this file twice.
      setRegister(await exportRiskRegister(cid));
    } catch (err) {
      setError(describeRiskError(err));
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-ink-secondary">Loading…</p>;
  }

  if (!cid) {
    return (
      <EmptyState
        title="Pick a client first"
        description="The Risk Register is generated per client. Choose a client from the switcher, then return here."
        action={
          <Link
            href="/admin/management"
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Go to Management
          </Link>
        }
      />
    );
  }

  // UNLOCKED but not synthesizable: the inputs exist and are unapproved (#237).
  // Rendered BEFORE the locked branch is irrelevant — the two are disjoint, and
  // this one has to exist at all so the refusal is visible before it is hit. A
  // consultant who unlocks the gate, clicks generate and meets a 409 has walked
  // into a wall the UI told them was not there, which is worse than a lock.
  // Gated on `synthesizable_missing`, NOT `not_finalized`. The latter reports
  // every unapproved input; only some of them block. Gating on the reporting
  // field would tell a consultant to approve an assessment that is not required
  // and is still being worked on.
  //
  // A BANNER INSIDE THE PAGE, never an early return. The first version returned
  // an EmptyState above every other branch, which took the whole page with it:
  // an existing register generated and exported last week -- its version, its
  // entries, its heatmap and the XLSX/PDF/Word download links to artifacts the
  // client already holds -- vanished the moment a consultant started a new
  // draft assessment. A state that blocks the NEXT register is not a reason to
  // hide the LAST one.
  //
  // It also dropped `<h1>Risk Register</h1>`, which is the shape CLAUDE.md
  // records: when a heading renders in every state except one, "heading
  // visible" silently becomes a proxy for "the page works", and a spec waiting
  // on it fails as a timeout rather than as an assertion.
  const blocking = gate?.synthesizable_missing ?? [];
  const blockedFromGenerating = Boolean(gate?.unlocked) && blocking.length > 0;
  // #556: blocks too, with its own sentence and remedy -- see the type.
  const catalogMismatch = gate?.unlocked
    ? (gate.attack_catalog_mismatch ?? null)
    : null;
  // Inputs that existed, were not approved, did not BLOCK (the unlock rule was
  // satisfied without them) and therefore contributed nothing. The `??` guards
  // `register` being null before anything is generated -- not an absent field,
  // which the API always sends.
  //
  // **This banner used to survive until the page was reloaded and no further**,
  // because nothing about the exclusion was persisted and
  // `GET .../register/latest` returned `[]`. All three of those claims are now
  // false: migration 0047 stores the set in `risk_registers.provenance`,
  // `_serialize` reads it back, and the banner is DERIVED from `register` on
  // every render rather than held in state.
  //
  // Kept and corrected rather than deleted, because the old text is what a
  // reader would otherwise act on -- and it was the THIRD copy of that claim.
  // The two in `lib/risk/types.ts` and `schemas/risk.py` were corrected by the
  // PR that fixed this; this one survived inside the file that PR rewrote,
  // which is the prose-sweep failure CLAUDE.md records: the sites someone was
  // handed get corrected, and the sentence saying the same thing in different
  // words lives on.
  //
  // What remains true: rendering it at generate is worth it because the moment
  // a consultant generates is the moment the omission is actionable.

  if (gate && !gate.unlocked) {
    return (
      <EmptyState
        title="Risk Register is locked"
        description={`To synthesise risks for ${clientName}, first complete: ${gate.missing.join("; ")}.`}
      />
    );
  }

  const tc = register?.tier_counts ?? {};
  const ac = register?.axis_counts ?? {};

  // #244. Derived per render from whatever response is in hand, rather than
  // carried in state. `?? []` covers only the no-register-yet case, where there
  // is nothing to disclose about.
  const excludedInputs = register?.excluded_inputs ?? [];
  // A register that predates provenance recording. `excluded_inputs` is `[]`
  // for it AND for a register that genuinely excluded nothing, so the flag is
  // the only thing that separates them -- and only one of the two deserves a
  // banner. Guarded on `register` so a page with nothing generated yet says
  // nothing rather than announcing a gap in a record that does not exist.
  const exclusionsNotRecorded =
    register != null && !register.excluded_inputs_recorded;

  return (
    <div className="flex flex-col gap-6">
      {excludedInputs.length > 0 ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="risk-register-excluded-inputs"
        >
          {/* #683: in number with the list -- "Those assessments ... them ...
              they" read one excluded assessment as several. */}
          Generated without {excludedInputs.join("; ")}.{" "}
          {excludedInputs.length === 1
            ? "That assessment exists but is not approved, so nothing from it is in this register. The exported documents do not say so — re-generate after approving it if it should be included."
            : "Those assessments exist but are not approved, so nothing from them is in this register. The exported documents do not say so — re-generate after approving them if they should be included."}
        </p>
      ) : null}

      {exclusionsNotRecorded ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="risk-register-exclusions-not-recorded"
        >
          This register was generated before SHIELD recorded which assessments
          were left out, so nothing on file says whether any were. That is not
          the same as none having been — re-generate to find out.
        </p>
      ) : null}

      {blockedFromGenerating ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="risk-register-unapproved-sources"
        >
          A new register cannot be generated until these are approved:{" "}
          {blocking.join("; ")}. Anything already generated below is unaffected.
        </p>
      ) : null}

      {catalogMismatch !== null ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="risk-register-attack-catalog-mismatch"
        >
          A new register cannot be generated from the ATT&amp;CK mapping.{" "}
          {catalogMismatch} Anything already generated below is unaffected.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink-primary">
            Risk Register
          </h1>
          <p className="mt-1 text-sm text-ink-secondary">
            {clientName}
            {register
              ? ` · version ${register.version}`
              : " · not yet generated"}
          </p>
          {/* The IA appendix asks whether the register is global, per-client or
              per-service. It is per-client, synthesized across that client's
              services — but the only place that was said is the "pick a client
              first" empty state, which anyone who already has a client selected
              never sees. Say it where it is actually read. */}
          <p className="text-sm text-ink-tertiary">
            Client-specific · synthesized across all of this client&apos;s
            services
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Issue 2: risk_synthesize is an AI job — warn before producing
              canned output when no key is loaded. */}
          <RunAiGuard onProceed={() => void onGenerate()}>
            {({ onClick }) => (
              <button
                type="button"
                onClick={onClick}
                // #556: a stale ATT&CK input's only outcome is the 409 the
                // banner above already explains, so the button is not offered.
                disabled={busy !== null || catalogMismatch !== null}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:opacity-50"
              >
                {busy === "generate"
                  ? "Generating…"
                  : register
                    ? "Regenerate"
                    : "Generate"}
              </button>
            )}
          </RunAiGuard>
          {register ? (
            <button
              type="button"
              onClick={onExport}
              disabled={busy !== null}
              className="rounded-md border border-border px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:opacity-50"
            >
              {busy === "export" ? "Exporting…" : "Export XLSX / PDF / Word"}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <p className="rounded-md bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg">
          {error}
        </p>
      ) : null}

      {!register ? (
        <Card>
          <CardBody>
            <p className="text-sm text-ink-secondary">
              No Risk Register yet. Generate one to synthesise the client&apos;s
              ATT&amp;CK, CSF, and Zero Trust gaps into a tiered register.
            </p>
          </CardBody>
        </Card>
      ) : (
        <>
          {/* #121. An entry with no tier renders as em dashes, is dropped from
              the 5x5 matrix, and is STILL counted by "Entries" -- so the card
              above can read 40 while the matrix sums to fewer, with nothing
              saying why.

              Two causes reach that state: a value the model supplied that
              would not resolve, and a key it simply omitted. The counter is
              keyed on the OUTCOME so it is non-zero under either, and it is
              derived server-side from the stored entries, so unlike the
              withheld-inputs banner below it survives a reload. */}
          {/* #372. A partial synthesis keeps what succeeded, so the register
              renders SHORT -- and until now nothing said so. The endpoint has
              always returned both counts; `lib/risk/types.ts` did not declare
              them, so they were dropped at the TypeScript boundary and the
              consultant exported a register missing a quarter of its entries
              with no indication. ATT&CK fixed the identical pair as #115.

              DURABLE, on every path. The tally is persisted in the register's
              provenance and `_serialize` reads it back, so generate, export
              and latest all report the run the register came from.

              An earlier revision of this comment claimed the banner was
              "transient by construction ... the same limitation the
              withheld-inputs banner below carries". BOTH HALVES WERE WRONG.
              The withheld-inputs banner is persisted and survives a reload --
              the comment two banners down says so in as many words -- so the
              parity was backwards, and citing it made a real defect read as an
              accepted limitation. The transience itself was not a limitation
              to document; it was the defect, and Export triggered it rather
              than merely failing to survive it.

              `=== null` is "nobody counted", which renders nothing: a register
              generated before this shipped carries no tally and must not be
              reported as complete OR as short. `> 0` on a non-null value is
              the loss. The two are distinguishable because the field is
              `number | null` rather than optional. */}
          {register.batches_failed !== null && register.batches_failed > 0 ? (
            <div
              className="rounded-md border border-status-danger-border bg-status-danger-bg p-3 text-sm text-status-danger-fg"
              role="alert"
              data-testid="risk-batches-failed"
            >
              <span className="font-semibold">
                {register.batches_failed} of {register.batches_total} synthesis
                batches failed
              </span>
              , so this register is INCOMPLETE -- the entries those batches
              would have produced are missing, not merely unscored. Regenerate
              before exporting. This notice is recorded with the register, so it
              survives an export and a reload and will still be here when you
              come back.
            </div>
          ) : null}
          {/* `!= null` catches BOTH null and undefined. `!== undefined` did
              not: no `exclude_none` exists in `apps/api`, so the wire sends
              `null` for every register predating this field -- that clause
              never discriminated, and the silence rested entirely on `null > n`
              coercing to false. An implicit coercion nobody wrote down was
              carrying the whole pre-#330 disclosure. */}
          {register.entries_intended != null &&
          register.entries_intended > register.entries_total ? (
            <div
              className="rounded-md border border-status-danger-border bg-status-danger-bg p-3 text-sm text-status-danger-fg"
              role="alert"
              data-testid="risk-entries-lost"
            >
              <span className="font-semibold">
                {register.entries_intended - register.entries_total} of{" "}
                {register.entries_intended} entries did not reach storage
              </span>
              , so every count below describes the {register.entries_total} that
              were stored, not the {register.entries_intended} the run intended.
              Regenerate before exporting: the deliverable reports the stored
              count with no note that anything is missing.
            </div>
          ) : null}
          {register.entries_without_tier > 0 ? (
            <div
              className="rounded-md border border-status-danger-border bg-status-danger-bg p-3 text-sm text-status-danger-fg"
              role="alert"
              data-testid="risk-entries-without-tier"
            >
              <span className="font-semibold">
                {register.entries_without_tier} of {register.entries_total}{" "}
                entries have no likelihood, impact or tier
              </span>
              , so they are missing from the matrix and the tier counts while
              still counting toward Entries. The model either sent a value that
              is not one of the accepted tokens, or sent none at all. The
              rejected values, if any, are on the{" "}
              <code>risk_register.generated</code> audit row. Regenerate before
              exporting: a client reading this register sees those rows as
              dashes.
            </div>
          ) : null}
          {/* #132. An entry that proposed ATT&CK or control links and kept
              none is persisted with empty link arrays -- byte-identical to an
              entry the model linked nothing for. The consultant reads "the AI
              found no relevance" over "the AI proposed five things and all
              five were misspelled".

              Keyed on the OUTCOME for the same reason the banner above is:
              `entries_with_dropped_links` counts entries with a spelling
              problem, which includes ones that kept a link and show linkage
              fine. This counts the ones with nothing left to show.

              Derived server-side from the stored entries, so it survives a
              reload -- which is what migration 0048 bought and the reason a
              counter on the generate response was not enough. */}
          {register.entries_unlinked_after_drops > 0 ? (
            <div
              className="rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm text-status-warning-fg"
              role="alert"
              data-testid="risk-entries-unlinked-after-drops"
            >
              <span className="font-semibold">
                {register.entries_unlinked_after_drops} of{" "}
                {register.entries_total} entries proposed ATT&amp;CK or control
                links and kept none
              </span>
              , so they show no linkage at all — the same as an entry nobody
              linked. Every value the model sent was either misnamed or names a
              control this client&apos;s assessments have not scored. A dropped
              source shows as <em>not recognised</em> in the Source column; the
              full values are on the <code>risk_register.generated</code> audit
              row. Where the cause is unscored assessment work rather than a
              misnamed value, regenerating returns the same rows and spends
              another model call. A client reading this register sees those rows
              as unlinked.
            </div>
          ) : null}
          {/* #132 review. Three counters exist because there are three
              states; one was rendered. These are the other two.

              `entries_with_dropped_links` is entries that lost a value and
              still show linkage. Lower severity than the banner above and not
              nothing: it is what a consultant fixes to stop the next run
              losing more.

              #403 CHANGED WHAT A DROP MEANS, and this comment said "the
              spelling problem" -- true when the allow-lists held every code
              that exists, so the only way to miss was to misname one. They now
              hold the codes an assessment SCORED, so a perfectly spelled,
              catalog-valid code is dropped when nobody has judged it. The two
              causes are not separable per value here; the scored-coverage
              banner below is what tells them apart at the assessment level.

              `entries_links_not_recorded` is pre-0048 rows, where "nothing was
              dropped" and "nobody was counting" are different facts. NOT
              hypothetical: `seed_demo.py` builds every RiskEntry without
              `dropped_links`, so the whole demo register is in this state, and
              without this it renders identically to a clean one. */}
          {register.entries_with_dropped_links >
          register.entries_unlinked_after_drops ? (
            <div
              className="rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
              data-testid="risk-entries-with-dropped-links"
            >
              <span className="font-semibold">
                {register.entries_with_dropped_links} of{" "}
                {register.entries_total} entries lost at least one value the
                model sent
              </span>{" "}
              — the rest of each still resolved, so they show linkage. The
              values are on each entry and on the{" "}
              <code>risk_register.generated</code> audit row. Worth a look
              before the next run: each is either a value the model misnamed or
              a control nobody has scored yet.
            </div>
          ) : null}
          {/* #403, the owner's three-state requirement. The VALUE tally, beside
              the ENTRY tallies above.

              THREE STATES, AND THE THIRD IS WHY THIS IS NOT A PLAIN NUMBER:
              `> 0` is a real count; `0` is a real count that happens to be
              zero, rendered so a consultant can read "nothing was discarded" as
              an OBSERVED fact; `null` is nobody counted, and renders NOTHING.

              A `null` must never render as "0 dropped". That is the UNCONFIRMED
              rule: a derived surface that cannot confirm its value never shows a
              plausible default, and "0 citations dropped" over a register nobody
              counted is a false assurance about the one population that cannot
              be re-checked (#372, #376).

              Rendering the zero rather than staying silent is deliberate and is
              the opposite decision from `null`: a counted zero is information a
              consultant wants before exporting, and it is the state that makes
              the silence of `null` legible by contrast.

              THE POPULATION TRAVELS WITH THE COUNT where part of the register
              could not be counted -- `entries_links_not_recorded` is what this
              tally could not see, and a scalar summed over a subset with nothing
              naming the subset is the partial-read-as-whole-answer defect. */}
          {register.dropped_citations !== null ? (
            <div
              className="rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
              data-testid="risk-citations-dropped"
            >
              <span className="font-semibold">
                {register.dropped_citations === 0
                  ? "No citation values were discarded"
                  : `${register.dropped_citations} citation value${
                      register.dropped_citations === 1 ? " was" : "s were"
                    } discarded`}
              </span>
              {register.entries_links_not_recorded > 0 ? (
                <>
                  {" "}
                  across the{" "}
                  {register.entries_total -
                    register.entries_links_not_recorded}{" "}
                  of {register.entries_total} entries that carry a link record —{" "}
                  {register.entries_links_not_recorded} predate link recording
                  and are not in this count.
                </>
              ) : (
                <> across all {register.entries_total} entries.</>
              )}{" "}
              This counts VALUES; the entry tallies above count ROWS, so one
              entry that lost three techniques is 1 there and 3 here.
            </div>
          ) : null}
          {register.entries_links_not_recorded > 0 ? (
            <div
              className="rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
              data-testid="risk-entries-links-not-recorded"
            >
              <span className="font-semibold">
                {register.entries_links_not_recorded} of{" "}
                {register.entries_total} entries predate link recording
              </span>
              , so nothing on file says whether the model proposed linkage for
              them. That is not the same as nothing having been dropped.
              Regenerate to find out.
            </div>
          ) : null}
          {/* #403. WHY the links are sparse, which none of the counters above
              can say.

              Those describe what the MODEL got wrong. This describes what the
              ASSESSMENT does not contain. The synthesis allow-lists are the
              codes a client's assessments actually SCORED, so a client who
              scored 12 of 700 techniques gets links drawn from 12 -- sparse
              linkage is CORRECT and reads as a regression.

              WITHOUT THIS THE FIX IS A REGRESSION IN DISGUISE: a silently
              wrong citation would have been traded for a silently missing one,
              which is the worse of the two. That is the whole reason this
              renders.

              RENDERED WHENEVER RECORDED, not only when something was excluded.
              A run that scored everything is a real answer a consultant should
              be able to read off the page, and gating on `excluded > 0` would
              make "fully scored" and "predates the recording" the same blank --
              the two-state trap the `_recorded` flag exists to end.

              The denominator travels with the count deliberately: a withheld
              number over an undisclosed population is not self-describing.

              THE LENGTH CHECK IS NOT THE TWO-STATE COLLAPSE IT LOOKS LIKE, and
              the distinction is worth reading before anyone "simplifies" it. The
              states that must stay apart are "fully scored" and "never
              recorded" -- and a fully scored assessment still produces a ROW
              (`{scored: 106, total: 106}`), so it is `recorded` AND non-empty.
              An empty array under `recorded: true` means the run recorded a
              scope naming no assessment at all, which `generate` cannot produce
              (it 409s on `synthesizable_missing`, so at least one assessment is
              always finalized). Rendering it would put this panel's heading and
              its "links can only cite what each assessment has scored" claim
              over nothing. */}
          {register.excluded_unscored_links_recorded &&
          register.excluded_unscored_links.length > 0 ? (
            <div
              className="rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
              data-testid="risk-link-scope"
            >
              <span className="font-semibold">
                Links can only cite what each assessment has scored
              </span>
              <ul className="mt-1 list-disc pl-5">
                {register.excluded_unscored_links.map((s) => (
                  <li key={s.service}>
                    {SERVICE_LABELS[s.service] ?? s.service}: {s.scored} of{" "}
                    {s.total} scored
                    {s.total > s.scored
                      ? `, ${s.total - s.scored} not yet judged and therefore not citable`
                      : " — every row judged"}
                  </li>
                ))}
              </ul>
              <p className="mt-1">
                An unscored control is unfinished assessment work, not a model
                error: regenerating cannot add links for rows nobody has judged.
                Score the outstanding rows first if this register should link
                more widely.
              </p>
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <NumberCard label="Entries" value={register.entries.length} />
            <NumberCard
              label="Critical + High"
              value={(tc.critical ?? 0) + (tc.high ?? 0)}
              deltaTone="negative"
            />
            <NumberCard label="Detection" value={ac.detection ?? 0} />
            <NumberCard label="Prevention" value={ac.prevention ?? 0} />
            <NumberCard label="Response" value={ac.response ?? 0} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Likelihood × Impact</CardTitle>
              <CardDescription>
                NIST 800-30 5×5. Each cell counts the entries that land there;
                colour is the derived tier.
              </CardDescription>
            </CardHeader>
            <CardBody>
              <Matrix entries={register.entries} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Register</CardTitle>
              <CardDescription>
                Tier is always code-derived from likelihood × impact. Governance
                columns (owner, approval, review) print blank for the client.
              </CardDescription>
            </CardHeader>
            <CardBody className="flex flex-col gap-4">
              <DataTable
                columns={COLUMNS}
                rows={register.entries}
                rowKey={(r) => r.id}
                emptyState={
                  <p className="p-4 text-sm text-ink-secondary">
                    No entries — the synthesis found no open gaps.
                  </p>
                }
              />
              {register.xlsx_artifact_id ||
              register.pdf_artifact_id ||
              register.docx_artifact_id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-ink-secondary">Downloads:</span>
                  <DownloadLink
                    id={register.xlsx_artifact_id}
                    filename={register.xlsx_filename}
                    label="XLSX"
                  />
                  <DownloadLink
                    id={register.pdf_artifact_id}
                    filename={register.pdf_filename}
                    label="PDF"
                  />
                  <DownloadLink
                    id={register.docx_artifact_id}
                    filename={register.docx_filename}
                    label="Word"
                  />
                </div>
              ) : (
                <p className="text-sm text-ink-tertiary">
                  Export to generate downloadable XLSX / PDF / Word files.
                </p>
              )}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
