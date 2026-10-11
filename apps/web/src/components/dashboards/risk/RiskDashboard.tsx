"use client";

import dynamic from "next/dynamic";
import * as React from "react";

import {
  C,
  DashResponsiveStyle,
  DashShell,
  KpiCard,
  KpiRow,
  Section,
} from "@/components/dashboards/shared";
import {
  IMPACT_ORDER,
  matrixGrid,
  tierColor,
  titleCase,
  type RiskDashboardData,
  type RiskEntry,
} from "@/lib/dashboards/risk";
import { targetSentences } from "@/lib/risk/baseline";
import { OTHER_AXES_HEADER, otherAxesCell } from "@/lib/risk/otherAxes";

import type { JSX } from "react";

const TierMixDonut = dynamic(
  () => import("./RiskCharts").then((m) => m.TierMixDonut),
  { ssr: false, loading: () => <div style={{ height: 300 }} aria-hidden /> },
);

function TierChip({ tier }: { tier: string | null }): JSX.Element {
  // #844: an entry with no tier is UNRATED, and says so. A dash read as a
  // value nobody filled in; the export prints the same words.
  if (!tier) return <span style={{ color: C.muted }}>Not rated</span>;
  const col = tierColor(tier);
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: ".05em",
        background: `${col}26`,
        color: col,
      }}
    >
      {tier}
    </span>
  );
}

function Matrix({ data }: { data: RiskDashboardData }): JSX.Element {
  const grid = matrixGrid(data.matrix); // rows: very_high → very_low
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "96px repeat(5, 1fr)",
        gap: 6,
      }}
    >
      {grid.map((row) => (
        <React.Fragment key={`row-${row[0].likelihood}`}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              paddingRight: 8,
              fontSize: 11,
              color: C.muted,
              textAlign: "right",
            }}
          >
            {titleCase(row[0].likelihood)}
          </div>
          {row.map((cell) => {
            const col = tierColor(cell.tier);
            return (
              <div
                key={`${cell.likelihood}-${cell.impact}`}
                title={`${titleCase(cell.likelihood)} × ${titleCase(cell.impact)} — ${cell.tier} (${cell.count})`}
                style={{
                  aspectRatio: "1.6 / 1",
                  minHeight: 44,
                  borderRadius: 8,
                  border: `1px solid ${col}55`,
                  background: `${col}1f`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: 15,
                  color: cell.count > 0 ? col : "rgba(152,162,196,.5)",
                }}
              >
                {cell.count > 0 ? cell.count : "·"}
              </div>
            );
          })}
        </React.Fragment>
      ))}
      {/* Impact axis labels */}
      <div />
      {IMPACT_ORDER.map((im) => (
        <div
          key={`im-${im}`}
          style={{
            textAlign: "center",
            fontSize: 11,
            color: C.muted,
            paddingTop: 4,
          }}
        >
          {titleCase(im)}
        </div>
      ))}
    </div>
  );
}

function AxisBars({ counts }: { counts: Record<string, number> }): JSX.Element {
  const axes = ["prevention", "detection", "response"];
  const max = Math.max(1, ...axes.map((a) => counts[a] ?? 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {axes.map((a) => {
        const n = counts[a] ?? 0;
        return (
          <div
            key={a}
            style={{ display: "flex", alignItems: "center", gap: 12 }}
          >
            <div style={{ width: 88, fontSize: 12.5, color: C.text }}>
              {titleCase(a)}
            </div>
            <div
              style={{
                flex: 1,
                height: 12,
                borderRadius: 999,
                background: "rgba(255,255,255,.06)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${(n / max) * 100}%`,
                  borderRadius: 999,
                  background: "linear-gradient(90deg, #6366f1, #22d3ee)",
                }}
              />
            </div>
            <div
              style={{
                width: 28,
                textAlign: "right",
                fontSize: 12.5,
                color: C.muted,
              }}
            >
              {n}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function cell(muted = false): React.CSSProperties {
  return {
    padding: "10px 12px",
    borderBottom: "1px solid rgba(255,255,255,.05)",
    verticalAlign: "top",
    color: muted ? C.muted : undefined,
  };
}

function th(): React.CSSProperties {
  return {
    position: "sticky",
    top: 0,
    background: C.bg2,
    color: C.muted,
    textAlign: "left",
    padding: "10px 12px",
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: ".06em",
    fontSize: 11,
    borderBottom: `1px solid ${C.border}`,
  };
}

/**
 * #854 F4, Gene's ruling (#736 item 9): the remedy names something the CLIENT
 * can do. The wording holds at any count. Gene ruled it on #736 6060627178 and
 * tightened it on 6064328745 (for #943), so that it cannot be read as every
 * entry in "Of {total} entries" rather than only the missing ones. The first
 * ruling replaced "Ask your consultant to complete those entries." Changing it
 * is this one product line plus two pinned test literals: `REMEDY` in
 * RiskDashboard.count-nouns.test.tsx and the regex in RiskDashboard.test.tsx.
 */
const WITHHELD_REMEDY =
  "Ask your consultant to complete each entry counted as missing above.";

export function RiskDashboard({
  data,
}: {
  data: RiskDashboardData;
}): JSX.Element {
  const tc = data.tier_counts;
  // #313. The qualifier existed, was computed, and reached the ADMIN only --
  // `_serialize` publishes it and `RiskRegisterDashboard.tsx` banners it, and
  // that banner's own copy ends by saying a client reading this register sees
  // those rows as dashes. The admin was told the client sees the undisclosed
  // version, and this surface was left in exactly that state.
  //
  // THREE states, not two. `undefined` is a register serialized before the
  // field existed: nobody looked. `0` is looked-and-nothing-withheld, which
  // is silence. Anything else is the disagreement and gets announced.
  // #313. One count per breakdown, because `tiers`, `axes` and `actions`
  // filter INDEPENDENTLY in `risk_dashboard`. A single count derived from
  // `tiers` left this silent while `axis_counts` summed short -- the defect
  // this banner exists to disclose, under a disclosure certifying its absence.
  //
  // NO not-recorded state, and the first version was wrong to have one. These
  // are computed per request and required in `RiskDashboardResponse`, so the
  // API always sends them; `undefined` was a state the server cannot produce,
  // and the branch handling it was production code for an unreachable input
  // with a test built to exercise it. That pattern belongs to PERSISTED
  // fields (#316's `excluded_inputs`), which this is not.
  const gaps: Array<[string, number]> = (
    [
      ["the 5x5 matrix and the tier counts", data.entries_without_tier],
      ["the axis breakdown", data.entries_without_axis],
      ["the action breakdown", data.entries_without_action],
    ] as Array<[string, number]>
  ).filter(([, n]) => n > 0);
  // #854 F4 (Gene's ruling, #736 item 9). The remedy names something the
  // CLIENT can do; "Regenerate before exporting" named an admin control, and
  // "as dashes" became false when unrated cells began to read "Not rated".
  //
  // A RATCHET UNDER D1: once #737 lands, publish refuses while any entry is
  // unrated, so a published register can carry no untiered entry and the tier
  // half of this banner cannot fire from any current writer. It stays, because
  // a register published before that gate, or a future path that loosens it,
  // would otherwise reach the client with nothing said.
  const withheldNote =
    gaps.length > 0 ? (
      <span>
        {/* #743: the counts below overlap (one entry can be missing from two
            breakdowns), so how many DISTINCT entries are affected is not
            known here. "At least one" is true in every state that renders
            (advisor, #736 6054419744). */}
        <span className="font-semibold">
          At least one entry is counted in Open risks and missing from a
          breakdown below.
        </span>{" "}
        Of {data.total_entries} {data.total_entries === 1 ? "entry" : "entries"}
        :{" "}
        {gaps.map(([label, n], i) => (
          <span key={label}>
            {i > 0 ? "; " : ""}
            {n} missing from {label}
          </span>
        ))}
        . Each is counted separately because each breakdown filters
        independently — an entry can carry a valid tier and still be missing
        from the axis chart. {WITHHELD_REMEDY}
      </span>
    ) : null;
  return (
    <DashShell
      aiSource={data.ai_source}
      title="Risk Register"
      subtitle="Synthesized 5×5 NIST 800-30 register · inherent risk across your services"
      releasedAt={data.released_at}
      version={data.version}
    >
      {withheldNote ? (
        <div
          className="mb-4 rounded-md border border-status-danger-border bg-status-danger-bg p-3 text-sm text-status-danger-fg"
          role="alert"
          data-testid="risk-entries-without-tier"
        >
          {withheldNote}
        </div>
      ) : null}
      {/* #474. Which target the findings were measured against, in the words
          the exported register prints, so the client can compare it with the
          target their CSF or Zero Trust report states. */}
      <div
        className="mb-4 text-sm"
        style={{ color: C.muted }}
        data-testid="risk-targets-used"
      >
        {targetSentences(
          data.targets,
          data.targets_recorded,
          data.csf_no_shared_row,
        ).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      {/* #915 (S3): the API's own sentence for the DoD target cap
          (`risk/zt_capped.py`), the one the register's files print, rendered
          as given. #944: keep it immediately after the target lines, whose
          last is the Zero Trust one, so the two read as one baseline. */}
      {data.zt_capped_target_note ? (
        <p
          className="mb-4 rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
          data-testid="risk-zt-capped-target"
        >
          {data.zt_capped_target_note}
        </p>
      ) : null}
      {/* #474 D' (Gene, #736 5984256202): where the register's CSF risks come
          from, in the API's own sentence (`risk/csf_source.py`), rendered as
          given. Null when the register has no CSF findings. */}
      {data.csf_source_note ? (
        <p
          className="mb-4 rounded-md border border-border bg-surface-sunken p-3 text-sm text-ink-secondary"
          data-testid="risk-csf-source"
        >
          {data.csf_source_note}
        </p>
      ) : null}
      <KpiRow>
        <KpiCard
          label="Open risks"
          value={String(data.total_entries)}
          sub="Across all services"
        />
        <KpiCard
          label="Critical"
          value={String(data.critical_count)}
          sub="Highest inherent risk"
          accent={C.red}
        />
        <KpiCard
          label="High"
          value={String(data.high_count)}
          sub="Elevated inherent risk"
          accent={C.amber}
        />
        <KpiCard
          label="Medium"
          value={String(tc.medium ?? 0)}
          sub="Moderate inherent risk"
          accent={C.accent2}
        />
      </KpiRow>

      <div
        className="dash-two"
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: 18,
          marginBottom: 18,
        }}
      >
        <Section
          title="Likelihood × Impact matrix"
          pill="5×5"
          desc="Inherent risk by likelihood (rows) and impact (columns); color is the code-derived tier."
        >
          <Matrix data={data} />
        </Section>
        <Section
          title="Risk tier mix"
          desc="How the register breaks down by severity."
        >
          <div style={{ position: "relative", height: 300 }}>
            <TierMixDonut counts={data.tier_counts} />
          </div>
        </Section>
      </div>

      <Section
        title="Inherent risk by SHIELD axis"
        desc="How many risks fall on each defensive axis."
      >
        <AxisBars counts={data.axis_counts} />
      </Section>

      <Section
        title="Full register"
        pill={`${data.entries.length} ${data.entries.length === 1 ? "entry" : "entries"}`}
      >
        <div
          style={{
            maxHeight: 560,
            overflowY: "auto",
            border: `1px solid ${C.border}`,
            borderRadius: 10,
          }}
        >
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 12.5,
            }}
          >
            <thead>
              <tr>
                <th style={th()}>Risk</th>
                <th style={th()}>Axis</th>
                <th style={th()}>{OTHER_AXES_HEADER}</th>
                <th style={th()}>Likelihood</th>
                <th style={th()}>Impact</th>
                <th style={th()}>Tier</th>
                <th style={th()}>Recommended action</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((e: RiskEntry, i) => (
                <tr key={i}>
                  <td style={{ ...cell(), fontWeight: 600, maxWidth: 360 }}>
                    {e.title}
                  </td>
                  <td style={cell(true)}>{e.axis ? titleCase(e.axis) : "—"}</td>
                  <td style={cell(true)}>{otherAxesCell(e.other_axes)}</td>
                  <td style={cell(true)}>
                    {e.likelihood ? titleCase(e.likelihood) : "Not rated"}
                  </td>
                  <td style={cell(true)}>
                    {e.impact ? titleCase(e.impact) : "Not rated"}
                  </td>
                  <td style={cell()}>
                    <TierChip tier={e.tier} />
                  </td>
                  <td style={cell(true)}>
                    {e.recommended_action
                      ? titleCase(e.recommended_action)
                      : "—"}
                  </td>
                </tr>
              ))}
              {data.entries.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    style={{ padding: 16, color: C.muted, textAlign: "center" }}
                  >
                    No risk entries.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Section>

      <DashResponsiveStyle />
    </DashShell>
  );
}
