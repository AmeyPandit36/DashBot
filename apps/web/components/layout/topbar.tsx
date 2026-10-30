"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, LogOut, Menu, Search, Sparkles, UserRound } from "lucide-react";
import { ThemeToggle } from "@/components/common/theme-toggle";
import { Logo } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";

const LABELS: Record<string, string> = {
  app: "Workspace",
  datasets: "Datasets",
  dashboards: "Dashboards",
  analyst: "AI Analyst",
  insights: "Insights",
  semantic: "Semantic models",
  settings: "Settings",
};

export function Topbar({ onMenu, llmEnabled }: { onMenu: () => void; llmEnabled: boolean }) {
  const pathname = usePathname();
  const { session, logout } = useAuth();
  const segments = pathname.split("/").filter(Boolean).slice(1);

  const crumbs = segments.map((segment, index) => ({
    label: LABELS[segment] ?? decodeURIComponent(segment).replace(/-/g, " ").slice(0, 18),
    href: `/app/${segments.slice(0, index + 1).join("/")}`,
  }));

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line/10 bg-bg/72 px-4 backdrop-blur-xl sm:px-6">
      <button
        type="button"
        onClick={onMenu}
        className="rounded-lg p-2 text-muted transition hover:bg-line/[0.06] hover:text-ink lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </button>

      <Link href="/app" className="lg:hidden" aria-label="Agentic BI home">
        <Logo showWordmark={false} />
      </Link>

      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 text-[12px] sm:flex">
        <Link href="/app" className="text-muted transition hover:text-ink">Workspace</Link>
        {crumbs.map((crumb, index) => (
          <span key={crumb.href} className="flex min-w-0 items-center gap-1.5">
            <ChevronRight className="h-3 w-3 shrink-0 text-faint" />
            {index === crumbs.length - 1 ? (
              <span className="truncate font-medium capitalize text-ink">{crumb.label}</span>
            ) : (
              <Link href={crumb.href} className="truncate capitalize text-muted transition hover:text-ink">
                {crumb.label}
              </Link>
            )}
          </span>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <Link
          href="/app/analyst"
          className="hidden items-center gap-2 rounded-xl border border-line/10 bg-surface/60 px-3 py-1.5 text-[11.5px] text-muted transition hover:border-brand/30 hover:text-ink md:flex"
        >
          <Search className="h-3.5 w-3.5" />
          Ask the analyst…
          <kbd className="rounded border border-line/15 px-1 py-0.5 text-[9.5px] text-faint">↵</kbd>
        </Link>
        <Badge tone={llmEnabled ? "brand" : "neutral"} className="hidden sm:inline-flex">
          <Sparkles className="h-3 w-3" />
          {llmEnabled ? "Gemini" : "Deterministic"}
        </Badge>
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand/20 to-violet/20 text-[11px] font-semibold text-ink ring-1 ring-inset ring-line/10"
              aria-label="Account menu"
            >
              {(session?.user.full_name ?? session?.user.email ?? "U").slice(0, 1).toUpperCase()}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-[220px]">
            <DropdownMenuLabel>
              <span className="block truncate text-[12px] font-medium text-ink">{session?.user.full_name}</span>
              <span className="block truncate text-[10.5px] font-normal text-muted">{session?.user.email}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/app/settings"><UserRound className="h-3.5 w-3.5" /> Profile & settings</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/app/settings"><Sparkles className="h-3.5 w-3.5" /> AI configuration</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => { void logout(); }}
              className="text-danger focus:text-danger"
            >
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button asChild variant="gradient" size="sm" className="hidden lg:inline-flex">
          <Link href="/app/datasets">Upload data</Link>
        </Button>
      </div>
    </header>
  );
}
