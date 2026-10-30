"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { PlatformConfig } from "@/lib/types";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { data: config } = useApi<PlatformConfig>("/meta/config");

  useEffect(() => setNavOpen(false), [pathname]);

  useEffect(() => {
    if (!loading && !session) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, session, router, pathname]);

  if (loading || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="flex flex-col items-center gap-3">
          <span className="relative flex h-10 w-10 items-center justify-center">
            <span className="absolute inset-0 animate-ping rounded-full bg-brand/25" />
            <span className="relative h-3 w-3 rounded-full bg-brand" />
          </span>
          <p className="text-[12px] text-muted">{loading ? "Loading your workspace…" : "Redirecting to sign in…"}</p>
          {!loading && (
            <Button asChild variant="outline" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg">
      <div className="app-ambient" aria-hidden />
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="lg:pl-[264px]">
        <Topbar onMenu={() => setNavOpen(true)} llmEnabled={Boolean(config?.llm.enabled)} />
        <main className="relative mx-auto w-full max-w-[1440px] px-4 pb-14 pt-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
