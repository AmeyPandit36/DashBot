"use client";

import { BadgeCheck, ShieldAlert, ShieldX, HelpCircle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { VerificationCheck } from "@/lib/types";
import { cn } from "@/components/ui/utils";

export function VerificationBadge({
  status,
  checks,
  className,
}: {
  status?: string | null;
  checks?: VerificationCheck[];
  className?: string;
}) {
  const config =
    status === "verified"
      ? { icon: BadgeCheck, label: "Verified", classes: "border-success/25 bg-success/10 text-success" }
      : status === "unverified"
        ? { icon: ShieldAlert, label: "Needs review", classes: "border-warning/25 bg-warning/10 text-warning" }
        : status === "failed"
          ? { icon: ShieldX, label: "Not verified", classes: "border-danger/25 bg-danger/10 text-danger" }
          : { icon: HelpCircle, label: "Unverified", classes: "border-line/15 bg-line/[0.05] text-muted" };
  const Icon = config.icon;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium", config.classes, className)}>
          <Icon className="h-3.5 w-3.5" />
          {config.label}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {checks?.length ? (
          <ul className="space-y-1.5">
            {checks.map((check) => (
              <li key={check.name} className="flex items-start gap-1.5">
                <span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", check.passed ? "bg-success" : "bg-danger")} />
                <span>
                  <span className="font-medium">{check.name.replace(/_/g, " ")}</span> — {check.detail}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <span>Numerical claims are checked against executed query results.</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
