"use client";

import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/components/ui/utils";
import { Card } from "@/components/ui/card";

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  delta,
  tone = "brand",
  loading = false,
}: {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;
  hint?: string;
  delta?: number | null;
  tone?: "brand" | "violet" | "cyan" | "teal" | "warning";
  loading?: boolean;
}) {
  const toneStyles: Record<string, string> = {
    brand: "from-brand/18 to-brand/5 text-brand",
    violet: "from-violet/18 to-violet/5 text-violet",
    cyan: "from-cyan/18 to-cyan/5 text-cyan",
    teal: "from-teal/18 to-teal/5 text-teal",
    warning: "from-warning/20 to-warning/5 text-warning",
  };

  return (
    <Card className="group relative overflow-hidden p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-faint">{label}</p>
          {loading ? (
            <div className="mt-3 h-8 w-28 skeleton" />
          ) : (
            <p className="kpi-value mt-2 text-[26px] font-semibold leading-none text-ink">{value}</p>
          )}
          {hint && <p className="mt-2 truncate text-[12px] text-muted">{hint}</p>}
        </div>
        {Icon && (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br border border-line/10", toneStyles[tone])}>
            <Icon className="h-4 w-4" strokeWidth={1.8} />
          </span>
        )}
      </div>
      {delta !== undefined && delta !== null && (
        <div className="mt-3 flex items-center gap-1.5 text-[12px]">
          <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium", delta >= 0 ? "bg-success/10 text-success" : "bg-danger/10 text-danger")}>
            {delta >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {Math.abs(delta).toFixed(1)}%
          </span>
          <span className="text-faint">vs previous period</span>
        </div>
      )}
      <div className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-brand-gradient opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-[0.12]" />
    </Card>
  );
}
