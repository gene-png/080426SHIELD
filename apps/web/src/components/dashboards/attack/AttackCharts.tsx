"use client";

import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  type ChartOptions,
  Legend,
  LinearScale,
  ArcElement,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import type { DashRollup } from "@/lib/dashboards/attack";
import { coverageMix, tacticBar } from "@/lib/dashboards/attack";

import type { JSX } from "react";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
);

const GREEN = "#10b981";
const AMBER = "#f59e0b";
const RED = "#ef4444";
const TEXT = "#e6e9f5";
const MUTED = "#98a2c4";
const GRID = "rgba(255,255,255,.06)";

/** Horizontal stacked bar: covered/partial/uncovered per tactic. */
export function TacticBarChart({
  byTactic,
}: {
  byTactic: DashRollup["by_tactic"];
}): JSX.Element {
  const bar = tacticBar(byTactic);
  const options: ChartOptions<"bar"> = {
    indexAxis: "y",
    plugins: {
      legend: {
        labels: { color: TEXT, boxWidth: 12, padding: 10, font: { size: 11 } },
        position: "bottom",
      },
    },
    scales: {
      x: {
        stacked: true,
        grid: { color: GRID },
        ticks: { color: MUTED, stepSize: 1, precision: 0 },
      },
      y: {
        stacked: true,
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
            label: "Covered",
            data: bar.covered,
            backgroundColor: GREEN,
            borderRadius: 4,
          },
          {
            label: "Partial",
            data: bar.partial,
            backgroundColor: AMBER,
            borderRadius: 4,
          },
          {
            label: "Uncovered",
            data: bar.gap,
            backgroundColor: RED,
            borderRadius: 4,
          },
        ],
      }}
    />
  );
}

/** Doughnut: overall coverage mix. */
export function CoverageMixDonut({
  rollup,
}: {
  rollup: DashRollup;
}): JSX.Element {
  const mix = coverageMix(rollup);
  const options: ChartOptions<"doughnut"> = {
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: TEXT, boxWidth: 12, padding: 14, font: { size: 12 } },
      },
    },
    cutout: "66%",
    maintainAspectRatio: false,
  };
  return (
    <Doughnut
      options={options}
      data={{
        labels: ["Covered", "Partial", "Uncovered"],
        datasets: [
          {
            data: [mix.covered, mix.partial, mix.gap],
            backgroundColor: [GREEN, AMBER, RED],
            borderColor: "#11172d",
            borderWidth: 3,
          },
        ],
      }}
    />
  );
}
