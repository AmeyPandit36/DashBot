"use client";

import Link from "next/link";
import { ArrowUpRight, Layers, Shapes } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Dataset } from "@/lib/types";

export default function SemanticModelsPage() {
  const { workspace } = useAuth();
  const { data, loading } = useApi<Dataset[]>(workspace ? `/datasets?workspace_id=${workspace.id}` : null);
  const datasets = (data ?? []).filter((dataset) => dataset.semantic_status);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Model"
        title="Semantic models"
        description="The approved business layer sits between your data and every dashboard or answer. Metrics, dimensions and time grains are versioned and human-approved."
      />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1].map((i) => <Card key={i} className="p-5"><Skeleton className="h-4 w-48" /><Skeleton className="mt-4 h-3 w-32" /></Card>)}
        </div>
      ) : datasets.length === 0 ? (
        <div className="glass rounded-2xl">
          <EmptyState
            icon={Shapes}
            title="No semantic models yet"
            description="Upload a dataset. A semantic model is proposed automatically from column statistics — then you review and approve it."
          />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {datasets.map((dataset) => (
            <Link key={dataset.id} href={`/app/semantic/${dataset.id}`} className="glass glass-hover group rounded-2xl p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet/12 text-violet">
                    <Layers className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-display text-[14.5px] font-semibold text-ink">{dataset.name}</p>
                    <p className="text-[11.5px] text-muted">Semantic v{dataset.semantic_version} · dataset v{dataset.active_version}</p>
                  </div>
                </div>
                <Badge tone={dataset.semantic_status === "approved" ? "success" : dataset.semantic_status === "proposed" ? "warning" : "neutral"}>
                  {dataset.semantic_status}
                </Badge>
              </div>
              <div className="mt-4 flex items-center justify-between text-[11.5px] text-muted">
                <span>{dataset.row_count.toLocaleString()} rows · quality {dataset.quality_score}</span>
                <span className="flex items-center gap-1 font-medium text-brand opacity-0 transition group-hover:opacity-100">
                  {dataset.semantic_status === "approved" ? "Inspect" : "Review"} <ArrowUpRight className="h-3.5 w-3.5" />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
