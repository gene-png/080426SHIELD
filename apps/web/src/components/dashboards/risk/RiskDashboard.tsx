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

import type { JSX } from "react";

const TierMixDonut = dynamic(
  () => import("./RiskCharts").then((m) => m.TierMixDonut),
  { ssr: false, loading: () => <div style={{ height: 300 }} aria-hidden /> },
);

function TierChip({ tier }: { tier: string | null }): JSX.Element {
  if (!tier) return <span style={{ color: C.muted }}>—</span>;
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

export function RiskDashboard({
  data,
}: {
  data: RiskDashboardData;
}): JSX.Element {
  const tc = data.tier_counts;
  return (
    <DashShell
      title="Risk Register"
      subtitle="Synthesized 5×5 NIST 800-30 register · inherent risk across your services"
      releasedAt={data.released_at}
      version={data.version}
    >
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

      <Section title="Full register" pill={`${data.entries.length} entries`}>
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
                  <td style={cell(true)}>
                    {e.likelihood ? titleCase(e.likelihood) : "—"}
                  </td>
                  <td style={cell(true)}>
                    {e.impact ? titleCase(e.impact) : "—"}
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
                    colSpan={6}
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
