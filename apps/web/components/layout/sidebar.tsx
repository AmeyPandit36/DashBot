"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3, Bot, Database, LayoutDashboard, Lightbulb, Shapes, Settings, Sparkles, X,
} from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { WorkspaceSwitcher } from "@/components/layout/workspace-switcher";
import { cn } from "@/components/ui/utils";
import { useAuth } from "@/lib/auth";

const GROUPS = [
  {
    label: "Analyse",
    items: [
      { href: "/app", label: "Overview", icon: LayoutDashboard, exact: true },
      { href: "/app/datasets", label: "Datasets", icon: Database },
      { href: "/app/dashboards", label: "Dashboards", icon: BarChart3 },
      { href: "/app/analyst", label: "AI Analyst", icon: Bot, badge: "AI" },
      { href: "/app/insights", label: "Insights", icon: Lightbulb },
    ],
  },
  {
    label: "Model",
    items: [{ href: "/app/semantic", label: "Semantic models", icon: Shapes }],
  },
  {
    label: "Configure",
    items: [{ href: "/app/settings", label: "Settings", icon: Settings }],
  },
];

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { session } = useAuth();

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-[#070B18]/50 backdrop-blur-sm transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          "sidebar fixed inset-y-0 left-0 z-50 flex w-[264px] flex-col border-r border-line/10 bg-surface/85 backdrop-blur-xl transition-transform duration-300 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between px-5">
          <Link href="/app" aria-label="Agentic BI home" onClick={onClose}>
            <Logo />
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-line/[0.06] lg:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-3">
          <WorkspaceSwitcher />
        </div>

        <nav className="mt-5 flex-1 space-y-5 overflow-y-auto px-3 pb-4">
          {GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-faint">{group.label}</p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.href, (item as { exact?: boolean }).exact);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onClose}
                        data-active={active}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-[12.5px] font-medium transition",
                          active
                            ? "bg-brand/[0.10] text-ink"
                            : "text-muted hover:bg-line/[0.05] hover:text-ink",
                        )}
                      >
                        <span
                          className={cn(
                            "absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-brand transition-opacity",
                            active ? "opacity-100" : "opacity-0",
                          )}
                        />
                        <Icon className={cn("h-[16px] w-[16px]", active ? "text-brand" : "text-faint group-hover:text-ink")} />
                        <span className="flex-1">{item.label}</span>
                        {"badge" in item && item.badge ? (
                          <span className="rounded-md bg-gradient-to-r from-brand/15 to-violet/15 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-brand">
                            {item.badge}
                          </span>
                        ) : null}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-line/10 p-3">
          <div className="rounded-xl bg-gradient-to-br from-brand/[0.10] via-violet/[0.08] to-transparent p-3">
            <p className="flex items-center gap-1.5 text-[11.5px] font-semibold text-ink">
              <Sparkles className="h-3.5 w-3.5 text-brand" /> SQL-backed answers
            </p>
            <p className="mt-1 text-[10.5px] leading-relaxed text-muted">
              Every number is computed by DuckDB and verified against its query result.
            </p>
          </div>
          {session && (
            <p className="mt-3 truncate px-1 text-[10.5px] text-faint">
              {session.organization.name} · {session.organization.plan}
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
