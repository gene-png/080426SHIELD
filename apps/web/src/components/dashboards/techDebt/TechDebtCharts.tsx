"use client";

import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  type ChartOptions,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import {
  spendBar,
  sprawlDonut,
  usdFull,
  type CategorySpend,
} from "@/lib/dashboards/techDebt";

import type { JSX } from "react";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
);

const TEXT = "#e6e9f5";
const MUTED = "#98a2c4";
const GRID = "rgba(255,255,255,.05)";
const SPRAWL_PALETTE = [
  "#ef4444",
  "#f59e0b",
  "#f97316",
  "#eab308",
  "#a855f7",
  "#6366f1",
  "#22d3ee",
  "#10b981",
  "#ec4899",
];

/** Annual spend by category (top 10), horizontal bar. */
export function SpendByCategory({
  spend,
}: {
  spend: CategorySpend[];
}): JSX.Element {
  const bar = spendBar(spend, 10);
  const options: ChartOptions<"bar"> = {
    indexAxis: "y",
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: (c) => usdFull(c.raw as number) } },
    },
    scales: {
      x: {
        grid: { color: GRID },
        ticks: { color: MUTED, callback: (v) => `$${Number(v) / 1000}K` },
      },
      y: {
        grid: { display: false },
        ticks: { color: TEXT, font: { size: 11 } },
      },
    },
    maintainAspectRatio: false,
  };
  return (
    <Bar
      options={options}
      data={{
        labels: bar.labels,
        datasets: [
          {
            data: bar.values,
            backgroundColor: bar.labels.map(
              (_, i) => `hsl(${230 - i * 8}, 70%, ${62 - i * 2}%)`,
            ),
            borderRadius: 6,
            borderSkipped: false,
          },
        ],
      }}
    />
  );
}

/** Tool sprawl by domain (categories with >1 tool), doughnut. */
export function ToolSprawl({
  sprawl,
}: {
  sprawl: CategorySpend[];
}): JSX.Element {
  const d = sprawlDonut(sprawl);
  const options: ChartOptions<"doughnut"> = {
    plugins: {
      legend: {
        position: "right",
        labels: { color: TEXT, font: { size: 11 }, boxWidth: 10, padding: 8 },
      },
      tooltip: { callbacks: { label: (c) => `${c.label}: ${c.raw} tools` } },
    },
    cutout: "62%",
    maintainAspectRatio: false,
  };
  return (
    <Doughnut
      options={options}
      data={{
        labels: d.labels,
        datasets: [
          {
            data: d.values,
            backgroundColor: d.labels.map(
              (_, i) => SPRAWL_PALETTE[i % SPRAWL_PALETTE.length],
            ),
            borderColor: "#11172d",
            borderWidth: 2,
          },
        ],
      }}
    />
  );
}
