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
  filterItems,
  usdCompact,
  usdFull,
  type Redundancy,
  type TechDebtDashboardData,
  type TechDebtItem,
} from "@/lib/dashboards/techDebt";

import type { JSX } from "react";

const SpendByCategory = dynamic(
  () => import("./TechDebtCharts").then((m) => m.SpendByCategory),
  { ssr: false, loading: () => <div style={{ height: 340 }} aria-hidden /> },
);
const ToolSprawl = dynamic(
  () => import("./TechDebtCharts").then((m) => m.ToolSprawl),
  { ssr: false, loading: () => <div style={{ height: 340 }} aria-hidden /> },
);

const DISPOSITION: Record<string, { bg: string; fg: string; label: string }> = {
  keep: { bg: "rgba(16,185,129,.18)", fg: "#a7f3d0", label: "Keep" },
  consolidate: {
    bg: "rgba(245,158,11,.18)",
    fg: "#fde68a",
    label: "Consolidate",
  },
  cut: { bg: "rgba(239,68,68,.18)", fg: "#fecaca", label: "Cut" },
};

/** The spend card's subtitle. THREE outcomes, mirroring the API's tri-state.
 *
 * #126: this card read "Across all tools" unconditionally, over a figure that
 * is a floor whenever an item has no cost or a source row was excluded. The
 * savings card directly beside it has carried "Floor - some cut tools lacked a
 * cost" since it was written; the asymmetry was the defect.
 *
 * "unknown" is deliberately not phrased as a floor. A floor is a claim that the
 * true figure is at least this much AND that something is missing; for a list
 * that was never reconciled we know only that nobody checked. Saying "Floor"
 * there would assert a defect nobody observed, which is the mirror image of
 * calling the figure a total.
 *
 * The card LABEL is deliberately unchanged: `e2e/smoke/s29-tech-debt-dashboard.spec.ts`
 * asserts `getByText("Annual license spend", { exact: true })`, and the
 * disclosure belongs in the subtitle beside it either way.
 */
export function spendSub(data: TechDebtDashboardData): string {
  if (data.spend_completeness === "unknown") {
    return "May not be complete - upload not reconciled";
  }
  if (data.spend_completeness === "partial") {
    if (data.excluded_count > 0 && data.source_rows_total !== null) {
      return `Floor - ${data.excluded_count} of ${data.source_rows_total} uploaded rows excluded`;
    }
    // The API reports "partial" for THREE causes and this renderer must not
    // guess which. `spend_completeness` is a three-valued label over a
    // four-state world, so the unbalanced case -- more items than there were
    // source rows -- arrives here indistinguishable from an uncosted tool.
    //
    // Saying "some tools lacked a cost" for it would be a precise, checkable
    // FALSEHOOD: in that state every tool is costed, and a client who went
    // looking for the uncosted one would find nothing. A vague label converted
    // into a confident wrong sentence is worse than the vague label.
    //
    // These two numbers are on the response, so the cause is recoverable here
    // without the `attribution_complete` migration that naming it precisely
    // would need (#193).
    if (
      data.source_rows_total !== null &&
      data.included_count > data.source_rows_total
    ) {
      return "Floor - upload does not reconcile";
    }
    return "Floor - some tools lacked a cost";
  }
  return "Across all tools";
}

function DispositionChip({ value }: { value: string | null }): JSX.Element {
  if (!value || !DISPOSITION[value]) {
    return <span style={{ color: C.muted, fontSize: 11.5 }}>—</span>;
  }
  const d = DISPOSITION[value];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
        background: d.bg,
        color: d.fg,
      }}
    >
      {d.label}
    </span>
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

function th(align: "left" | "right" = "left"): React.CSSProperties {
  return {
    position: "sticky",
    top: 0,
    background: C.bg2,
    color: C.muted,
    textAlign: align,
    padding: "10px 12px",
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: ".06em",
    fontSize: 11,
    borderBottom: `1px solid ${C.border}`,
  };
}

function RedundancyCard({ r }: { r: Redundancy }): JSX.Element {
  return (
    <div
      style={{
        background: C.bg2,
        border: `1px solid ${C.border}`,
        borderLeft: `3px solid ${r.savings_usd > 0 ? C.amber : C.accent}`,
        borderRadius: 12,
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{ display: "flex", justifyContent: "space-between", gap: 10 }}
      >
        <div style={{ fontWeight: 700, fontSize: 14 }}>
          {r.category}{" "}
          <span style={{ color: C.muted, fontWeight: 400 }}>
            · {r.count} tools
          </span>
        </div>
        {r.savings_usd > 0 ? (
          <span style={{ color: "#a7f3d0", fontWeight: 700, fontSize: 12.5 }}>
            {usdCompact(r.savings_usd)}/yr
          </span>
        ) : null}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {r.items.map((it) => (
          <div
            key={it.name}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12.5,
            }}
          >
            <DispositionChip value={it.disposition} />
            <span>{it.name}</span>
            <span style={{ marginLeft: "auto", color: C.muted }}>
              {usdCompact(it.annual_cost_usd)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TechDebtDashboard({
  data,
}: {
  data: TechDebtDashboardData;
}): JSX.Element {
  const [q, setQ] = React.useState("");
  const rows = filterItems(data.items, q);

  return (
    <DashShell
      title={data.service_title}
      subtitle="Software portfolio · Spend, sprawl, and consolidation savings"
      releasedAt={data.released_at}
      version={data.deliverable_version}
    >
      <KpiRow>
        <KpiCard
          label="Applications"
          value={String(data.total_applications)}
          sub="Tools in the portfolio"
        />
        <KpiCard
          label="Annual license spend"
          value={usdFull(data.annual_spend_usd)}
          sub={spendSub(data)}
          accent={C.accent2}
        />
        <KpiCard
          label="Redundant categories"
          value={String(data.redundant_category_count)}
          sub="Categories with 2+ overlapping tools"
          accent={C.amber}
        />
        <KpiCard
          label="Identified savings"
          value={usdFull(data.identified_savings_usd)}
          sub={
            data.savings_cost_known
              ? "From tools marked to cut"
              : "Floor — some cut tools lacked a cost"
          }
          accent={C.green}
        />
      </KpiRow>

      <div
        className="dash-two"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 18,
          marginBottom: 18,
        }}
      >
        <Section
          title="Annual spend by category"
          desc="Where the budget concentrates."
        >
          <div style={{ position: "relative", height: 340 }}>
            <SpendByCategory spend={data.spend_by_category} />
          </div>
        </Section>
        <Section
          title="Tool sprawl by domain"
          desc="Categories carrying more than one tool."
        >
          <div style={{ position: "relative", height: 340 }}>
            <ToolSprawl sprawl={data.sprawl_by_category} />
          </div>
        </Section>
      </div>

      {data.redundancies.length > 0 ? (
        <Section
          title="Functional redundancies"
          pill={`${data.redundancies.length} categories`}
          desc="Overlapping tools and the consolidation the analyst has marked."
        >
          <div
            className="dash-three"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 14,
            }}
          >
            {data.redundancies.map((r) => (
              <RedundancyCard key={r.category} r={r} />
            ))}
          </div>
        </Section>
      ) : null}

      <Section
        title="Full software inventory"
        pill={`${data.items.length} tools`}
      >
        <div style={{ marginBottom: 12 }}>
          <input
            aria-label="Search inventory"
            placeholder="Search product, vendor, category, or function…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{
              width: "100%",
              maxWidth: 420,
              background: C.bg2,
              color: C.text,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              padding: "8px 12px",
              fontSize: 13,
              outline: "none",
            }}
          />
        </div>
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
                <th style={th()}>Product</th>
                <th style={th()}>Vendor</th>
                <th style={th()}>Category</th>
                <th style={th()}>Function</th>
                <th style={th("right")}>Annual cost</th>
                <th style={th("right")}>Licenses</th>
                <th style={th()}>Disposition</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((it: TechDebtItem) => (
                <tr key={it.name}>
                  <td style={{ ...cell(), fontWeight: 600 }}>{it.name}</td>
                  <td style={cell(true)}>{it.vendor ?? "—"}</td>
                  <td style={cell(true)}>{it.category ?? "—"}</td>
                  <td style={cell(true)}>{it.function ?? "—"}</td>
                  <td style={{ ...cell(), textAlign: "right" }}>
                    {usdCompact(it.annual_cost_usd)}
                  </td>
                  <td style={{ ...cell(true), textAlign: "right" }}>
                    {it.license_count ?? "—"}
                  </td>
                  <td style={cell()}>
                    <DispositionChip value={it.disposition} />
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    style={{ padding: 16, color: C.muted, textAlign: "center" }}
                  >
                    No tools match your search.
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
