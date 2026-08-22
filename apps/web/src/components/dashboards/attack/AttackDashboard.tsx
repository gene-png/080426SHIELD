"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";

import {
  blindSpots,
  dprCoverage,
  filterTechniques,
  kpis,
  tacticOptions,
  type AttackDashboardData,
  type DashTechnique,
  type DprLeg,
} from "@/lib/dashboards/attack";

import type { JSX } from "react";

// Charts are client-only (Chart.js touches <canvas>); load without SSR.
const TacticBarChart = dynamic(
  () => import("./AttackCharts").then((m) => m.TacticBarChart),
  { ssr: false, loading: () => <ChartSkeleton /> },
);
const CoverageMixDonut = dynamic(
  () => import("./AttackCharts").then((m) => m.CoverageMixDonut),
  { ssr: false, loading: () => <ChartSkeleton /> },
);

// Mockup palette (Atlas_MITRE_Coverage_Dashboard.html). Kept inline so the dark
// executive surface is self-contained regardless of the app's light tokens.
const C = {
  bg: "#0b1020",
  bg2: "#11172d",
  panelFrom: "#151b35",
  panelTo: "#1a2143",
  border: "#232a4d",
  text: "#e6e9f5",
  muted: "#98a2c4",
  accent: "#6366f1",
  accent2: "#22d3ee",
  green: "#10b981",
  amber: "#f59e0b",
  red: "#ef4444",
};

const panel: React.CSSProperties = {
  background: `linear-gradient(180deg, ${C.panelFrom} 0%, ${C.panelTo} 100%)`,
  border: `1px solid ${C.border}`,
  borderRadius: 16,
};

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function ChartSkeleton(): JSX.Element {
  return <div style={{ height: 320 }} aria-hidden />;
}

function Section({
  title,
  pill,
  desc,
  children,
}: {
  title: string;
  pill?: string;
  desc?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section style={{ ...panel, padding: 22, marginBottom: 18 }}>
      <h2
        style={{
          margin: "0 0 4px",
          fontSize: 16,
          fontWeight: 700,
          display: "flex",
          gap: 10,
          alignItems: "center",
        }}
      >
        {title}
        {pill ? (
          <span
            style={{
              fontSize: 11,
              padding: "3px 8px",
              borderRadius: 999,
              background: "rgba(99,102,241,.18)",
              color: "#c7d2fe",
              fontWeight: 600,
            }}
          >
            {pill}
          </span>
        ) : null}
      </h2>
      {desc ? (
        <p style={{ color: C.muted, fontSize: 13, margin: "0 0 16px" }}>
          {desc}
        </p>
      ) : null}
      {children}
    </section>
  );
}

function Ring({ pct, color }: { pct: number; color: string }): JSX.Element {
  const r = 40;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - pct / 100);
  return (
    <div style={{ position: "relative", width: 92, height: 92, flexShrink: 0 }}>
      <svg
        viewBox="0 0 96 96"
        style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}
      >
        <circle
          cx="48"
          cy="48"
          r={r}
          fill="none"
          stroke={C.border}
          strokeWidth="10"
        />
        <circle
          cx="48"
          cy="48"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={circ}
          strokeDashoffset={off}
          strokeLinecap="round"
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 700,
          fontSize: 18,
        }}
      >
        {pct}%
      </div>
    </div>
  );
}

const STATUS_CHIP: Record<string, { bg: string; fg: string; label: string }> = {
  covered: { bg: "rgba(16,185,129,.18)", fg: "#a7f3d0", label: "Covered" },
  partial: { bg: "rgba(245,158,11,.18)", fg: "#fde68a", label: "Partial" },
  gap: { bg: "rgba(239,68,68,.18)", fg: "#fecaca", label: "Uncovered" },
  not_applicable: { bg: "rgba(152,162,196,.18)", fg: "#cbd5e1", label: "N/A" },
  // #102. Its OWN state, and deliberately NOT the red of `gap`: a reader takes
  // the colour before the word, so reusing red would collapse "nothing was
  // found" into "something was found and is not confirmed" exactly where the
  // distinction matters. The underlying status is named in the label so the
  // reader can see what it will become once the evidence is confirmed.
  pending_review: {
    bg: "rgba(59,130,246,.18)",
    fg: "#bfdbfe",
    label: "Pending review",
  },
};

function Chip({
  status,
  pendingReview,
}: {
  status: string;
  pendingReview?: boolean;
}): JSX.Element {
  const base = STATUS_CHIP[status] ?? STATUS_CHIP.not_applicable;
  const s = pendingReview
    ? {
        ...STATUS_CHIP.pending_review,
        label: `Pending review (${base.label.toLowerCase()})`,
      }
    : base;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 9px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: ".06em",
        background: s.bg,
        color: s.fg,
      }}
    >
      {s.label}
    </span>
  );
}

function Leg({ on, label }: { on: boolean; label: string }): JSX.Element {
  return (
    <span
      title={label}
      style={{
        width: 22,
        height: 22,
        borderRadius: 6,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 10,
        fontWeight: 800,
        border: `1px solid ${on ? "rgba(16,185,129,.3)" : "rgba(239,68,68,.3)"}`,
        background: on ? "rgba(16,185,129,.18)" : "rgba(239,68,68,.12)",
        color: on ? "#a7f3d0" : "#fecaca",
      }}
    >
      {label}
    </span>
  );
}

export function AttackDashboard({
  data,
}: {
  data: AttackDashboardData;
}): JSX.Element {
  const k = kpis(data);
  const dpr = dprCoverage(data.techniques);
  const blind = blindSpots(data.techniques);
  const tactics = React.useMemo(
    () => tacticOptions(data.techniques),
    [data.techniques],
  );

  const [q, setQ] = React.useState("");
  const [tactic, setTactic] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const rows = filterTechniques(data.techniques, {
    q,
    tactic,
    status: statusFilter,
  });

  const releasedLabel = (() => {
    const d = new Date(data.released_at);
    return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
  })();

  const input: React.CSSProperties = {
    background: C.bg2,
    color: C.text,
    border: `1px solid ${C.border}`,
    borderRadius: 8,
    padding: "8px 12px",
    fontSize: 13,
    outline: "none",
  };

  return (
    <div style={{ background: C.bg, color: C.text, minHeight: "100vh" }}>
      <div
        style={{ maxWidth: 1440, margin: "0 auto", padding: "28px 24px 56px" }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
            marginBottom: 22,
          }}
        >
          <div>
            <Link
              href="/results"
              style={{ color: C.accent2, fontSize: 12, textDecoration: "none" }}
            >
              ← Back to results
            </Link>
            <h1 style={{ margin: "6px 0 0", fontSize: 22, fontWeight: 700 }}>
              {data.service_title}
            </h1>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: C.muted }}>
              MITRE ATT&amp;CK Coverage · Detect / Prevent / Respond posture
            </p>
          </div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "rgba(99,102,241,.12)",
              border: "1px solid rgba(99,102,241,.35)",
              color: "#c7d2fe",
              padding: "6px 12px",
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 999,
                background: C.green,
                boxShadow: "0 0 0 4px rgba(16,185,129,.18)",
              }}
            />
            Released {releasedLabel} · v{data.deliverable_version}
          </div>
        </div>

        {/* KPIs */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 16,
            marginBottom: 20,
          }}
          className="dash-kpis"
        >
          <KpiCard
            label="Techniques evaluated"
            value={String(k.evaluated)}
            sub="Coverage assessed this engagement"
          />
          <KpiCard
            label="Fully covered"
            value={`${k.covered.n} · ${k.covered.pct}%`}
            sub="Detection + prevention + response present"
            accent={C.green}
          />
          <KpiCard
            label="Partially covered"
            value={`${k.partial.n} · ${k.partial.pct}%`}
            sub="One or two triad legs present"
            accent={C.amber}
          />
          <KpiCard
            label="Blind spots"
            value={`${k.blindSpots.n} · ${k.blindSpots.pct}%`}
            sub="No meaningful coverage"
            accent={C.red}
          />
        </div>

        {/* Charts */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 18,
            marginBottom: 18,
          }}
          className="dash-charts"
        >
          <Section
            title="Coverage by tactic"
            desc="Where the kill chain is strong and where it breaks."
          >
            <div style={{ position: "relative", height: 340 }}>
              <TacticBarChart byTactic={data.rollup.by_tactic} />
            </div>
          </Section>
          <Section
            title="Overall coverage mix"
            desc={
              (data.rollup.pending_review ?? 0) > 0
                ? `Weighted coverage across evaluated techniques: ${data.rollup.coverage_pct}%. ` +
                  `${data.rollup.pending_review} technique${data.rollup.pending_review === 1 ? " is" : "s are"} ` +
                  `held out of this figure pending evidence review, so it is a percentage of what can be ` +
                  `claimed today — not of the whole catalogue.`
                : `Weighted coverage across evaluated techniques: ${data.rollup.coverage_pct}%.`
            }
          >
            <div style={{ position: "relative", height: 340 }}>
              <CoverageMixDonut rollup={data.rollup} />
            </div>
          </Section>
        </div>

        {/* DPR triad */}
        <Section
          title="Detect · Prevent · Respond posture"
          desc="A technique is fully covered only when all three legs are present."
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 14,
            }}
            className="dash-triad"
          >
            <TriadCard
              title="Detect"
              leg={dpr.detect}
              total={dpr.total}
              color={C.accent2}
              desc="Telemetry catches the technique — EDR, NDR, SIEM, or audit logs."
            />
            <TriadCard
              title="Prevent"
              leg={dpr.prevent}
              total={dpr.total}
              color={C.accent}
              desc="A control reduces the chance the technique succeeds."
            />
            <TriadCard
              title="Respond"
              leg={dpr.respond}
              total={dpr.total}
              color={C.green}
              desc="An automated playbook or runbook fires — not just manual triage."
            />
          </div>
        </Section>

        {/* Blind spots */}
        {blind.length > 0 ? (
          <Section
            title="What you're blind to today"
            pill={`${blind.length} uncovered`}
            desc="Techniques with no meaningful detection, prevention, or response."
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, 1fr)",
                gap: 14,
              }}
              className="dash-blind"
            >
              {blind.map((t) => (
                <div
                  key={t.code}
                  style={{
                    background: C.bg2,
                    border: `1px solid ${C.border}`,
                    borderLeft: `3px solid ${C.red}`,
                    borderRadius: 12,
                    padding: "16px 18px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 10,
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontFamily: "ui-monospace, Menlo, monospace",
                          fontSize: 11,
                          color: C.muted,
                        }}
                      >
                        {t.code}
                      </div>
                      <div style={{ fontWeight: 700, fontSize: 14 }}>
                        {t.name}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: ".08em",
                        padding: "3px 8px",
                        borderRadius: 999,
                        background: "rgba(239,68,68,.18)",
                        color: "#fecaca",
                      }}
                    >
                      {t.tactic_name}
                    </span>
                  </div>
                  {t.rationale ? (
                    <div
                      style={{
                        fontSize: 12.5,
                        color: C.muted,
                        lineHeight: 1.55,
                        marginTop: 8,
                      }}
                    >
                      {t.rationale}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </Section>
        ) : null}

        {/* Technique matrix */}
        <Section
          title="Per-technique coverage matrix"
          pill={`${data.techniques.length} techniques`}
        >
          <div
            style={{
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              marginBottom: 12,
            }}
          >
            <input
              aria-label="Search techniques"
              placeholder="Search technique ID, name, or tool…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ ...input, flex: 1, minWidth: 260 }}
            />
            <select
              aria-label="Filter by tactic"
              value={tactic}
              onChange={(e) => setTactic(e.target.value)}
              style={input}
            >
              <option value="">All tactics</option>
              {tactics.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by coverage"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={input}
            >
              <option value="">All coverage</option>
              <option value="covered">Covered</option>
              <option value="partial">Partial</option>
              <option value="gap">Uncovered</option>
              <option value="not_applicable">N/A</option>
            </select>
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
                  {[
                    "ID",
                    "Technique",
                    "Tactic",
                    "Coverage",
                    "D·P·R",
                    "Detection",
                    "Prevention",
                    "Response",
                  ].map((h) => (
                    <th
                      key={h}
                      style={{
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
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <MatrixRow key={t.code} t={t} />
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      style={{
                        padding: 16,
                        color: C.muted,
                        textAlign: "center",
                      }}
                    >
                      No techniques match your filters.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </Section>

        <footer
          style={{
            color: C.muted,
            fontSize: 11.5,
            textAlign: "center",
            marginTop: 24,
          }}
        >
          SHIELD · Confidential · Coverage as of the released assessment.
        </footer>
      </div>

      {/* Narrow screens: collapse the multi-column grids. */}
      <style>{`
        @media (max-width: 1080px) {
          .dash-kpis { grid-template-columns: repeat(2, 1fr) !important; }
          .dash-charts, .dash-triad, .dash-blind { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: string;
}): JSX.Element {
  return (
    <div
      style={{
        ...panel,
        padding: "20px 22px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          right: -30,
          top: -30,
          width: 120,
          height: 120,
          borderRadius: "50%",
          opacity: 0.14,
          background: `radial-gradient(circle, ${accent ?? C.accent}, transparent 70%)`,
        }}
      />
      <div
        style={{
          fontSize: 12,
          color: C.muted,
          textTransform: "uppercase",
          letterSpacing: ".08em",
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, marginTop: 8 }}>{value}</div>
      <div style={{ fontSize: 12, color: C.muted, marginTop: 6 }}>{sub}</div>
    </div>
  );
}

function TriadCard({
  title,
  leg,
  total,
  color,
  desc,
}: {
  title: string;
  leg: DprLeg;
  total: number;
  color: string;
  desc: string;
}): JSX.Element {
  return (
    <div
      style={{
        background: C.bg2,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        padding: "18px 20px",
        display: "flex",
        alignItems: "center",
        gap: 18,
      }}
    >
      <Ring pct={leg.pct} color={color} />
      <div>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{title}</div>
        <div style={{ fontSize: 12, color: C.muted, margin: "2px 0 6px" }}>
          {leg.n} of {total} techniques
        </div>
        <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.5 }}>
          {desc}
        </div>
      </div>
    </div>
  );
}

function toolCell(tools: string[]): string {
  return tools.length ? tools.join(", ") : "—";
}

function MatrixRow({ t }: { t: DashTechnique }): JSX.Element {
  return (
    <tr>
      <td style={cell({ mono: true })}>{t.code}</td>
      <td style={cell({ weight: 600 })}>{t.name}</td>
      <td style={cell()}>
        <span
          style={{
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: 999,
            fontSize: 11,
            background: "rgba(168,85,247,.15)",
            color: "#e9d5ff",
          }}
        >
          {t.tactic_name}
        </span>
      </td>
      <td style={cell()}>
        <Chip status={t.status} pendingReview={t.pending_review} />
      </td>
      <td style={cell()}>
        <span style={{ display: "inline-flex", gap: 4 }}>
          <Leg on={t.detection_tools.length > 0} label="D" />
          <Leg on={t.prevention_tools.length > 0} label="P" />
          <Leg on={t.response_tools.length > 0} label="R" />
        </span>
      </td>
      <td style={cell({ muted: true })}>{toolCell(t.detection_tools)}</td>
      <td style={cell({ muted: true })}>{toolCell(t.prevention_tools)}</td>
      <td style={cell({ muted: true })}>{toolCell(t.response_tools)}</td>
    </tr>
  );
}

function cell(
  opts: { mono?: boolean; weight?: number; muted?: boolean } = {},
): React.CSSProperties {
  return {
    padding: "10px 12px",
    borderBottom: "1px solid rgba(255,255,255,.05)",
    verticalAlign: "top",
    fontFamily: opts.mono ? "ui-monospace, Menlo, monospace" : undefined,
    fontWeight: opts.weight,
    color: opts.muted ? C.muted : undefined,
    fontSize: opts.mono ? 11.5 : undefined,
  };
}
