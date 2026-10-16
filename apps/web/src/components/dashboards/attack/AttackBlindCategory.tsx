"use client";

import type { JSX } from "react";

import { C, DashShell, Section } from "@/components/dashboards/shared";
import {
  blindByTactic,
  type AttackDashboardData,
} from "@/lib/dashboards/attack";

import { BlindSpotCard } from "./AttackDashboard";

/**
 * #1180 (Gene's 2026-10-15 item 12): one category of "What you're blind to
 * today", on its own page. Copy B-2 to B-4 approved verbatim (#736 comment
 * 6216024281). `slug` comes from the URL; a name that matches no category with
 * blind spots says so (B-4) rather than showing an empty page.
 */
export function AttackBlindCategory({
  data,
  slug,
}: {
  data: AttackDashboardData;
  slug: string;
}): JSX.Element {
  const group = blindByTactic(data).find((g) => g.slug === slug) ?? null;
  return (
    <DashShell
      aiSource={data.ai_source}
      title={data.service_title}
      subtitle="MITRE ATT&CK Coverage · Detect / Prevent / Respond posture"
      releasedAt={data.released_at}
      version={data.deliverable_version}
      footer="SHIELD · Confidential · Coverage as of the released assessment."
    >
      <p style={{ margin: "0 0 12px" }}>
        <a
          href={`/dashboards/attack/${data.service_id}`}
          data-testid="attack-blind-back"
          style={{ color: C.accent2, fontSize: 13 }}
        >
          Back to the ATT&amp;CK dashboard
        </a>
      </p>
      {group === null ? (
        <p data-testid="attack-blind-none" style={{ color: C.muted }}>
          No uncovered techniques in this category.
        </p>
      ) : (
        <Section title={`What you're blind to today: ${group.tactic}`}>
          <div
            data-testid="attack-blind-category-cards"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 14,
            }}
            className="dash-blind"
          >
            {group.rows.map((t) => (
              <BlindSpotCard key={t.code} t={t} />
            ))}
          </div>
        </Section>
      )}
    </DashShell>
  );
}
