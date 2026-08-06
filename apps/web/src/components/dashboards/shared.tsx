import Link from "next/link";
import * as React from "react";

import type { JSX } from "react";

/**
 * Shared presentational primitives for the client-facing executive dashboards
 * (D-035). The mockup palette is kept inline so each dashboard is a
 * self-contained dark surface regardless of the app's light shell.
 */

export const C = {
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
  purple: "#a855f7",
};

export const panel: React.CSSProperties = {
  background: `linear-gradient(180deg, ${C.panelFrom} 0%, ${C.panelTo} 100%)`,
  border: `1px solid ${C.border}`,
  borderRadius: 16,
};

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

/** Full-bleed dark shell: back link, title/subtitle, and a released badge. */
export function DashShell({
  title,
  subtitle,
  releasedAt,
  version,
  children,
}: {
  title: string;
  subtitle: string;
  releasedAt: string;
  version: number;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div style={{ background: C.bg, color: C.text, minHeight: "100vh" }}>
      <div
        style={{ maxWidth: 1440, margin: "0 auto", padding: "28px 24px 56px" }}
      >
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
              ← Back to documents
            </Link>
            <h1 style={{ margin: "6px 0 0", fontSize: 22, fontWeight: 700 }}>
              {title}
            </h1>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: C.muted }}>
              {subtitle}
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
            Released {formatDate(releasedAt)} · v{version}
          </div>
        </div>
        {children}
        <footer
          style={{
            color: C.muted,
            fontSize: 11.5,
            textAlign: "center",
            marginTop: 24,
          }}
        >
          SHIELD · Confidential · Figures as of the released assessment.
        </footer>
      </div>
    </div>
  );
}

export function Section({
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

/** One KPI card with an optional accent glow. */
export function KpiCard({
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

export function KpiRow({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div
      className="dash-kpis"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 16,
        marginBottom: 20,
      }}
    >
      {children}
    </div>
  );
}

/** A progress ring (percentage) used by the D/P/R triad and maturity views. */
export function Ring({
  pct,
  color,
}: {
  pct: number;
  color: string;
}): JSX.Element {
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

/** Narrow-screen collapse for the dashboards' multi-column grids. */
export function DashResponsiveStyle(): JSX.Element {
  return (
    <style>{`
      @media (max-width: 1080px) {
        .dash-kpis { grid-template-columns: repeat(2, 1fr) !important; }
        .dash-two, .dash-triad, .dash-blind, .dash-three { grid-template-columns: 1fr !important; }
      }
    `}</style>
  );
}
