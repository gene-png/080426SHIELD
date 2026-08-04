"use client";

import {
  ArcElement,
  Chart as ChartJS,
  type ChartOptions,
  Legend,
  Tooltip,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";

import { tierMix } from "@/lib/dashboards/risk";

import type { JSX } from "react";

ChartJS.register(ArcElement, Tooltip, Legend);

const TEXT = "#e6e9f5";

/** Tier mix doughnut (critical/high/medium/low/negligible). */
export function TierMixDonut({
  counts,
}: {
  counts: Record<string, number>;
}): JSX.Element {
  const mix = tierMix(counts);
  const options: ChartOptions<"doughnut"> = {
    plugins: {
      legend: {
        position: "right",
        labels: { color: TEXT, font: { size: 12 }, boxWidth: 12, padding: 10 },
      },
      tooltip: { callbacks: { label: (c) => `${c.label}: ${c.raw} risks` } },
    },
    cutout: "62%",
    maintainAspectRatio: false,
  };
  return (
    <Doughnut
      options={options}
      data={{
        labels: mix.map((m) => m.label),
        datasets: [
          {
            data: mix.map((m) => m.value),
            backgroundColor: mix.map((m) => m.color),
            borderColor: "#11172d",
            borderWidth: 3,
          },
        ],
      }}
    />
  );
}
