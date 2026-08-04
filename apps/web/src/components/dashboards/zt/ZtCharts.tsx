"use client";

import {
  Chart as ChartJS,
  type ChartOptions,
  Filler,
  Legend,
  LineElement,
  PointElement,
  RadialLinearScale,
  Tooltip,
} from "chart.js";
import { Radar } from "react-chartjs-2";

import { radarData, type ZtPillar } from "@/lib/dashboards/zt";

import type { JSX } from "react";

ChartJS.register(
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

const TEXT = "#e6e9f5";
const MUTED = "#98a2c4";
const GRID = "rgba(255,255,255,.08)";

/** Current-vs-target maturity radar across the CISA/DoD pillars. */
export function MaturityRadar({
  pillars,
}: {
  pillars: ZtPillar[];
}): JSX.Element {
  const data = radarData(pillars);
  const options: ChartOptions<"radar"> = {
    plugins: {
      legend: {
        position: "bottom",
        labels: { color: TEXT, font: { size: 12 }, padding: 14, boxWidth: 14 },
      },
    },
    scales: {
      r: {
        min: 0,
        max: 100,
        grid: { color: GRID },
        angleLines: { color: GRID },
        pointLabels: { color: TEXT, font: { size: 12, weight: 600 } },
        ticks: {
          color: MUTED,
          backdropColor: "transparent",
          stepSize: 25,
          font: { size: 10 },
        },
      },
    },
    maintainAspectRatio: false,
  };
  return (
    <Radar
      options={options}
      data={{
        labels: data.labels,
        datasets: [
          {
            label: "Current",
            data: data.current,
            backgroundColor: "rgba(34, 211, 238, .18)",
            borderColor: "#22d3ee",
            borderWidth: 2,
            pointBackgroundColor: "#22d3ee",
            pointRadius: 4,
          },
          {
            label: "Target (12–18 mo)",
            data: data.target,
            backgroundColor: "rgba(16, 185, 129, .14)",
            borderColor: "#10b981",
            borderWidth: 2,
            borderDash: [6, 4],
            pointBackgroundColor: "#10b981",
            pointRadius: 4,
          },
        ],
      }}
    />
  );
}
