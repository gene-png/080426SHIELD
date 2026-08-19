"use client";

import {
  C,
  DashResponsiveStyle,
  DashShell,
  KpiCard,
  KpiRow,
  Section,
} from "@/components/dashboards/shared";
import {
  functionsByGap,
  hiddenGapCount,
  targetIsAssumed,
  type CsfDashboardData,
  type CsfFunction,
} from "@/lib/dashboards/csf";

import type { JSX } from "react";

function pctText(n: number | null): string {
  return n === null ? "—" : `${Math.round(n)}`;
}

/** One function's current→target bar. Mirrors ZT's per-pillar bar. */
function MaturityBar({ fn }: { fn: CsfFunction }): JSX.Element {
  const cur = fn.current_pct ?? 0;
  const tgt = fn.target_pct ?? 0;
  return (
    <div>
      <div
        style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 12 }}
      >
        <span style={{ color: "#c7d2fe", fontWeight: 700 }}>
          {fn.name} · {fn.current_label}
          {fn.current_pct === null ? "" : ` · ${pctText(fn.current_pct)}`}
        </span>
        <span style={{ color: C.muted }}>→</span>
        <span style={{ color: "#a7f3d0", fontWeight: 700 }}>
          {pctText(fn.target_pct)}
        </span>
        {/* An unassessed function has NO gap to move — its bar length is an
            artefact of comparing 0 against the target, and it sorts to the top
            of a list headed "largest move required". Say what it is instead of
            printing "0 gaps · +75 pt move" next to it. */}
        <span style={{ marginLeft: "auto", color: C.muted, fontSize: 11.5 }}>
          {fn.current_pct === null
            ? `Not assessed · 0 of ${fn.subcategory_count} scored`
            : `${fn.gap_count} gap${fn.gap_count === 1 ? "" : "s"} · +${Math.round(fn.gap_pct)} pt move · ${fn.answered_count}/${fn.subcategory_count} scored`}
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
      <div style={{ position: "relative", height: 0 }}>
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
        <span>Partial</span>
        <span>Risk Informed</span>
        <span>Repeatable</span>
        <span>Adaptive</span>
      </div>
    </div>
  );
}

export function CsfDashboard({
  data,
}: {
  data: CsfDashboardData;
}): JSX.Element {
  const ordered = functionsByGap(data.functions);
  const hidden = hiddenGapCount(data);
  const assumedTarget = targetIsAssumed(data);

  return (
    <DashShell
      title={data.service_title}
      subtitle="NIST CSF 2.0 · Current state vs target profile"
      releasedAt={data.released_at}
      version={data.deliverable_version}
    >
      <KpiRow>
        <KpiCard
          label="Functions assessed"
          value={String(data.functions.length)}
          sub={`${Math.round(data.coverage_pct)}% of subcategories scored`}
        />
        <KpiCard
          label="Current maturity"
          value={`${data.overall_label} · ${pctText(data.current_pct)}`}
          sub="Averaged across all functions"
          accent={C.accent2}
        />
        <KpiCard
          label="Target profile"
          value={`${data.target_label} · ${pctText(data.target_pct)}`}
          /* An assumed target is labelled as one. #73 shipped a client-facing
             document computing gaps against a hardcoded tier while the client
             had chosen a different one, so a number nobody picked read exactly
             like a number they did. */
          sub={
            assumedTarget
              ? "Default target — no tier chosen at intake"
              : "Your target, chosen at intake"
          }
          accent={C.green}
        />
        <KpiCard
          label="Largest gap"
          value={data.largest_gap_function ?? "—"}
          sub={`+${Math.round(data.largest_gap_pct)} points to target`}
          accent={C.amber}
        />
      </KpiRow>

      <Section
        title="Maturity by function"
        desc="Ordered by the largest move required to reach your target"
      >
        <div style={{ display: "grid", gap: 18 }}>
          {ordered.map((fn) => (
            <MaturityBar key={fn.code} fn={fn} />
          ))}
        </div>
      </Section>

      <Section
        title="Priority remediation"
        /* The truncation is DISCLOSED, always. #75 is open because the ZT
           exporter renders a slice with the true total nowhere on the page, so
           a client reads 20 of 37 items with no statement that anything was
           omitted. */
        desc={
          hidden > 0
            ? `Highest-priority ${data.top_gaps.length} of ${data.total_gap_count} gaps · ${hidden} more not shown`
            : `All ${data.total_gap_count} gap${data.total_gap_count === 1 ? "" : "s"}`
        }
      >
        {data.top_gaps.length === 0 ? (
          <p style={{ color: C.muted, fontSize: 13 }}>
            No subcategory is below your target profile.
          </p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {data.top_gaps.map((g) => (
              <div
                key={g.code}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 12,
                  fontSize: 12.5,
                  borderBottom: "1px solid rgba(255,255,255,.06)",
                  paddingBottom: 8,
                }}
              >
                <span style={{ color: C.muted, minWidth: 84 }}>{g.code}</span>
                <span style={{ color: "#e5e7eb", flex: 1 }}>{g.name}</span>
                <span style={{ color: C.muted }}>{g.function_name}</span>
                <span style={{ color: C.amber, fontWeight: 700 }}>
                  Tier {g.current_tier} → {g.target_tier}
                </span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <DashResponsiveStyle />
    </DashShell>
  );
}
