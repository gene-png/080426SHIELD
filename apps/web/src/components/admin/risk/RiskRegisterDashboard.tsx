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
      className="rounded-md border border-border-default px-3 py-1.5 text-sm font-medium text-ink-primary hover:bg-surface-muted"
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
  // HELD SEPARATELY FROM `register`, and that separation is the fix rather than
  // a style choice. `export` returns `_serialize(db, reg)` with no
  // `excluded_inputs`, which the schema defaults to `[]` -- so
  // `setRegister(await exportRiskRegister(cid))` overwrote the disclosure with
  // an empty list and the banner unmounted at the exact moment the consultant
  // did the thing it warns about. The withheld set is a property of what the
  // register was BUILT from; no later response can revise it, so no later
  // response gets to clear it either.
  const [excludedInputs, setExcludedInputs] = React.useState<string[]>([]);
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
        // `latest` always returns `[]` here (nothing is persisted -- #240), so
        // this seeds empty on a reload and the banner is generate-scoped. That
        // is the stated limitation, not an accident.
        setExcludedInputs(reg?.excluded_inputs ?? []);
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
      // The ONLY producer of a non-empty withheld set.
      setExcludedInputs(reg.excluded_inputs);
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
      // Deliberately does NOT touch `excludedInputs`. See the state
      // declaration: the export response cannot carry it, so assigning from
      // here would erase it.
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
  // Inputs that existed, were not approved, did not BLOCK (the unlock rule was
  // satisfied without them) and therefore contributed nothing. The `??` guards
  // `register` being null before anything is generated -- not an absent field,
  // which the API always sends.
  //
  // **This banner survives until the page is reloaded and no further**, because
  // nothing about the exclusion is persisted: `GET .../register/latest` returns
  // `[]`. That is #240, which needs a migration. It is worth rendering anyway --
  // the moment a consultant generates is the moment the omission is actionable,
  // and for one review round this field reached no surface at all, which made
  // "the register says so" true of nobody.

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

  return (
    <div className="flex flex-col gap-6">
      {excludedInputs.length > 0 ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="risk-register-excluded-inputs"
        >
          Generated without {excludedInputs.join("; ")}. Those assessments exist
          but are not approved, so nothing from them is in this register. The
          exported documents do not say so — re-generate after approving them if
          they should be included.
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
                disabled={busy !== null}
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
              className="rounded-md border border-border-default px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-muted disabled:opacity-50"
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
              linked. Every value the model sent named something that is not in
              this client&apos;s assessments. A dropped source shows as{" "}
              <em>not recognised</em> in the Source column; the full values are
              on the <code>risk_register.generated</code> audit row. Regenerate
              before exporting: a client reading this register sees those rows
              as unlinked.
            </div>
          ) : null}
          {/* #132 review. Three counters exist because there are three
              states; one was rendered. These are the other two.

              `entries_with_dropped_links` is the spelling problem -- entries
              that lost a value and still show linkage. Lower severity than the
              banner above and not nothing: it is what a consultant fixes to
              stop the next run losing more.

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
              before the next run: they are what the model keeps getting wrong.
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
