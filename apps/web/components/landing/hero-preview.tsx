"use client";

import { useTheme } from "next-themes";
import { ArrowUpRight, BadgeCheck, TrendingUp } from "lucide-react";
import { EChart } from "@/components/charts/echart";
import { useEffect, useState } from "react";

const months = ["Nov 25", "Dec 25", "Jan 26", "Feb 26", "Mar 26", "Apr 26", "May 26", "Jun 26", "Jul 26", "Aug 26", "Sep 26"];
const revenue = [119, 141, 128, 124, 118, 136, 149, 143, 138, 131, 122];
const orders = [101, 112, 106, 104, 99, 108, 115, 111, 109, 105, 100];

export function HeroPreview() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";

  const axis = dark ? "#9AA3C2" : "#545C7A";
  const split = dark ? "rgba(255,255,255,0.07)" : "rgba(21,27,50,0.07)";

  const option = {
    animationDuration: 900,
    grid: { left: 0, right: 6, top: 18, bottom: 0, containLabel: true },
    color: ["#4F6BFF", "#06B6D4"],
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(17,23,43,0.96)" : "rgba(255,255,255,0.97)",
      borderColor: split,
      textStyle: { color: dark ? "#ECF0FF" : "#151B32", fontSize: 11 },
    },
    xAxis: {
      type: "category",
      data: months,
      boundaryGap: false,
      axisLine: { lineStyle: { color: split } },
      axisTick: { show: false },
      axisLabel: { color: axis, fontSize: 9, interval: 2 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: axis, fontSize: 9, formatter: (v: number) => `₹${v}k` },
      splitLine: { lineStyle: { color: split, type: "dashed" } },
      axisLine: { show: false },
    },
    series: [
      {
        name: "Revenue",
        type: "line",
        smooth: 0.42,
        symbol: "none",
        lineStyle: { width: 2.4 },
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(79,107,255,0.30)" },
              { offset: 1, color: "rgba(79,107,255,0.02)" },
            ],
          },
        },
        data: revenue,
      },
      {
        name: "Orders",
        type: "line",
        smooth: 0.42,
        symbol: "none",
        lineStyle: { width: 1.8, type: "dashed" },
        data: orders,
      },
    ],
  };

  return (
    <div className="relative">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-brand-gradient opacity-[0.16] blur-3xl" aria-hidden />
      <div className="glass overflow-hidden rounded-3xl border-line/15 shadow-float">
        <div className="flex items-center justify-between border-b border-line/10 bg-surface/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="flex gap-1.5">
              <span className="h-2 w-2 rounded-full bg-danger/60" />
              <span className="h-2 w-2 rounded-full bg-warning/60" />
              <span className="h-2 w-2 rounded-full bg-success/60" />
            </span>
            <span className="ml-2 text-[11px] font-medium text-muted">Retail performance · live dashboard</span>
          </div>
          <span className="rounded-full border border-line/10 bg-surface/60 px-2 py-0.5 text-[9px] font-medium uppercase tracking-[0.12em] text-faint">
            Synthetic demo
          </span>
        </div>

        <div className="space-y-3 p-4">
          <div className="grid grid-cols-3 gap-2.5">
            {[
              { label: "Total revenue", value: "₹2.78M", delta: "+12.8%", tone: "text-success" },
              { label: "Orders", value: "6,640", delta: "+4.2%", tone: "text-success" },
              { label: "Avg order value", value: "₹419", delta: "−3.1%", tone: "text-danger" },
            ].map((kpi) => (
              <div key={kpi.label} className="rounded-xl border border-line/10 bg-surface/65 p-2.5">
                <p className="text-[9px] font-medium uppercase tracking-[0.1em] text-faint">{kpi.label}</p>
                <p className="kpi-value mt-1 text-[17px] font-semibold leading-none text-ink">{kpi.value}</p>
                <p className={`mt-1 text-[10px] font-medium ${kpi.tone}`}>{kpi.delta}</p>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-line/10 bg-surface/65 p-3">
            <div className="mb-1 flex items-center justify-between">
              <p className="text-[11px] font-semibold text-ink">Revenue & orders trend</p>
              <span className="flex items-center gap-1 text-[10px] text-success">
                <TrendingUp className="h-3 w-3" /> 24-month view
              </span>
            </div>
            <EChart option={option} height={132} ariaLabel="Illustrative revenue and order trend" />
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-line/10 bg-surface/65 px-3 py-2">
            <BadgeCheck className="h-4 w-4 shrink-0 text-success" />
            <p className="text-[10.5px] leading-snug text-muted">
              <span className="font-medium text-ink">North leads with ₹841,665</span> — 30.3% of revenue. Verified against DuckDB.
            </p>
            <ArrowUpRight className="ml-auto h-3.5 w-3.5 shrink-0 text-faint" />
          </div>
        </div>
      </div>

      <div className="absolute -bottom-8 -left-4 hidden w-[210px] rounded-2xl border border-line/12 bg-surface/90 p-3 shadow-float backdrop-blur-xl sm:block animate-float">
        <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-brand">Agent insight</p>
        <p className="mt-1.5 text-[11px] leading-relaxed text-ink">
          West region revenue fell 21.8% quarter on quarter, driven by deeper discounting.
        </p>
        <p className="mt-2 text-[9px] text-faint">Verified · 3 queries · DuckDB</p>
      </div>

      <div className="absolute -right-3 top-16 hidden rounded-xl border border-line/12 bg-surface/90 px-3 py-2 shadow-float backdrop-blur-xl md:block">
        <p className="text-[9px] uppercase tracking-[0.12em] text-faint">SQL provenance</p>
        <p className="mt-1 font-mono text-[10px] text-ink">SUM(total_amount) → ₹2.78M</p>
      </div>
    </div>
  );
}
