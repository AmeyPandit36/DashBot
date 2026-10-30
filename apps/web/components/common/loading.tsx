import { Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-96" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="glass rounded-2xl p-5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-4 h-7 w-32" />
            <Skeleton className="mt-3 h-3 w-20" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="glass rounded-2xl p-5 lg:col-span-2"><Skeleton className="h-56 w-full" /></div>
        <div className="glass rounded-2xl p-5"><Skeleton className="h-56 w-full" /></div>
      </div>
    </div>
  );
}

export function InlineLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin text-brand" />
      {label}…
    </div>
  );
}

export function FullScreenLoader({ label = "Preparing your workspace" }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas">
      <div className="relative flex h-14 w-14 items-center justify-center">
        <span className="absolute inset-0 rounded-2xl bg-brand-gradient opacity-25 blur-lg" />
        <span className="relative flex h-12 w-12 items-center justify-center rounded-2xl border border-line/10 bg-surface shadow-card">
          <Loader2 className="h-5 w-5 animate-spin text-brand" />
        </span>
      </div>
      <p className="text-sm text-muted">{label}…</p>
    </div>
  );
}
