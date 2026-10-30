import Link from "next/link";
import { BadgeCheck, Database, GitBranch, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/brand/logo";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen">
      <div className="pointer-events-none absolute inset-0 -z-10 aurora" aria-hidden />
      <div className="pointer-events-none absolute inset-0 -z-10 grid-lines opacity-60" aria-hidden />

      <div className="flex w-full flex-col px-5 py-8 sm:px-10 lg:w-[52%] lg:px-16">
        <Link href="/" className="w-fit" aria-label="Agentic BI home">
          <Logo />
        </Link>

        <div className="flex flex-1 items-center py-10">
          <div className="w-full max-w-[420px] animate-fade-up">
            <h1 className="font-display text-[28px] font-semibold tracking-[-0.03em] text-ink">{title}</h1>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">{subtitle}</p>
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-6 text-[13px] text-muted">{footer}</div>}
          </div>
        </div>

        <p className="text-[11px] text-faint">
          Protected workspace · tenant-isolated data · every answer verified against executed SQL
        </p>
      </div>

      <div className="relative hidden flex-1 overflow-hidden border-l border-line/10 lg:block">
        <div className="absolute inset-0 bg-gradient-to-br from-brand/[0.10] via-violet/[0.06] to-cyan/[0.08]" aria-hidden />
        <div className="relative flex h-full flex-col justify-between p-12">
          <div className="flex flex-wrap gap-2">
            {[
              { icon: Database, label: "DuckDB analytics" },
              { icon: GitBranch, label: "LangGraph agents" },
              { icon: ShieldCheck, label: "Read-only SQL policy" },
            ].map((pill) => (
              <span key={pill.label} className="inline-flex items-center gap-1.5 rounded-full border border-line/12 bg-surface/60 px-3 py-1 text-[11px] text-muted backdrop-blur">
                <pill.icon className="h-3 w-3 text-brand" /> {pill.label}
              </span>
            ))}
          </div>

          <div className="max-w-md">
            <p className="font-display text-[30px] font-medium leading-snug tracking-[-0.025em] text-ink">
              “It answered the questions our BI team needed a week to build — and showed the SQL behind every number.”
            </p>
            <div className="mt-6 flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-gradient text-[12px] font-semibold text-white">RK</span>
              <div>
                <p className="text-[13px] font-medium text-ink">Head of Revenue Operations</p>
                <p className="text-[11px] text-faint">Demonstration workspace</p>
              </div>
            </div>
          </div>

          <div className="glass rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <p className="text-[12px] font-semibold text-ink">Latest verified answer</p>
              <BadgeCheck className="h-4 w-4 text-success" />
            </div>
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted">
              Revenue is <span className="font-semibold text-ink">₹2.78M</span> across 6,640 orders. North leads at
              <span className="font-semibold text-ink"> ₹841,665</span> (30.3%).
            </p>
            <p className="mt-2 font-mono text-[10.5px] text-faint">1 query · 4 evidence rows · verified</p>
          </div>
        </div>
      </div>
    </div>
  );
}
