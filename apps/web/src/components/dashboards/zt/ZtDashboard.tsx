"use client";

import dynamic from "next/dynamic";

import {
  C,
  DashResponsiveStyle,
  DashShell,
  KpiCard,
  KpiRow,
  Section,
} from "@/components/dashboards/shared";
import {
  pillarsByGap,
  type ZtDashboardData,
  type ZtPillar,
} from "@/lib/dashboards/zt";

import type { JSX } from "react";

const MaturityRadar = dynamic(
  () => import("./ZtCharts").then((m) => m.MaturityRadar),
  { ssr: false, loading: () => <div style={{ height: 380 }} aria-hidden /> },
);

function pctText(n: number | null): string {
  return n === null ? "—" : `${Math.round(n)}`;
}

function MaturityBar({ pillar }: { pillar: ZtPillar }): JSX.Element {
  const cur = pillar.current_pct ?? 0;
  const tgt = pillar.target_pct ?? 0;
  return (
    <div>
      <div
        style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 12 }}
      >
        <span style={{ color: "#c7d2fe", fontWeight: 700 }}>
          {pillar.current_label} · {pctText(pillar.current_pct)}
        </span>
        <span style={{ color: C.muted }}>→</span>
        <span style={{ color: "#a7f3d0", fontWeight: 700 }}>
          {pillar.target_label} · {pctText(pillar.target_pct)}
        </span>
        <span style={{ marginLeft: "auto", color: C.muted, fontSize: 11.5 }}>
          +{Math.round(pillar.gap_pct)} pt move
        </span>
      </div>
      <div
        style={{
          position: "relative",
          height: 10,
          borderRadius: 999,
          background: "rgba(255,255,255,.06)",
          overflow: "hidden",
          marginTop: 8,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            height: "100%",
            width: `${cur}%`,
            borderRadius: 999,
            background: "linear-gradient(90deg, #22d3ee, #6366f1)",
          }}
        />
      </div>
      <div
        style={{
          position: "relative",
          height: 0,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: -13,
            left: `calc(${tgt}% - 1px)`,
            height: 16,
            width: 3,
            background: C.green,
            borderRadius: 2,
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: C.muted,
          marginTop: 4,
        }}
      >
        <span>Traditional</span>
        <span>Initial</span>
        <span>Advanced</span>
        <span>Optimal</span>
      </div>
    </div>
  );
}

export function ZtDashboard({ data }: { data: ZtDashboardData }): JSX.Element {
  const ordered = pillarsByGap(data.pillars);
  return (
    <DashShell
      title={data.service_title}
      subtitle={`${data.framework_label} · Current state vs 12–18 month target`}
      releasedAt={data.released_at}
      version={data.deliverable_version}
    >
      <KpiRow>
        <KpiCard
          label="Pillars assessed"
          value={String(data.pillars.length)}
          sub={data.framework_label}
        />
        <KpiCard
          label="Current maturity"
          value={`${data.current_label} · ${pctText(data.current_pct)}`}
          sub="Weighted across all pillars"
          accent={C.accent2}
        />
        <KpiCard
          label="Target maturity"
          value={`${data.target_label} · ${pctText(data.target_pct)}`}
          sub="12–18 month goal"
          accent={C.green}
        />
        <KpiCard
          label="Largest gap"
          value={data.largest_gap_pillar ?? "—"}
          sub={`+${Math.round(data.largest_gap_pct)} points to target`}
          accent={C.amber}
        />
      </KpiRow>

      <Section
        title="Maturity across the model"
        pill={`${data.pillars.length} dimensions`}
        desc="Where you sit today (cyan) vs the 12–18 month target (green)."
      >
        <div style={{ position: "relative", height: 380 }}>
          <MaturityRadar pillars={data.pillars} />
        </div>
      </Section>

      <Section
        title="Per-pillar deep dive"
        desc="Current maturity, the target, and the lowest-scored capabilities to focus on."
      >
        <div
          className="dash-two"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: 14,
          }}
        >
          {ordered.map((p) => (
            <div
              key={p.code}
              style={{
                background: C.bg2,
                border: `1px solid ${C.border}`,
                borderLeft: `4px solid ${C.accent}`,
                borderRadius: 14,
                padding: "18px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 700 }}>{p.name}</div>
              <MaturityBar pillar={p} />
              {p.weakest.length > 0 ? (
                <div>
                  <div
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: ".08em",
                      color: C.muted,
                      fontWeight: 600,
                      margin: "4px 0 6px",
                    }}
                  >
                    Focus areas
                  </div>
                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: 18,
                      fontSize: 12.5,
                      color: C.text,
                      lineHeight: 1.6,
                    }}
                  >
                    {p.weakest.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Section>

      <DashResponsiveStyle />
    </DashShell>
  );
}
