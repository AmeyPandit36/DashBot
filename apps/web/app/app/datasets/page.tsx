"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Database, FileSpreadsheet, Search, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { UploadDatasetDialog } from "@/components/dashboard/upload-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { relativeTime, qualityTone } from "@/lib/format";
import type { Dataset, Job } from "@/lib/types";

export default function DatasetsPage() {
  const { workspace } = useAuth();
  const router = useRouter();
  const workspaceId = workspace?.id;
  const { data, loading, refresh } = useApi<Dataset[]>(workspaceId ? `/datasets?workspace_id=${workspaceId}` : null);
  const [search, setSearch] = useState("");
  const [demoLoading, setDemoLoading] = useState(false);

  const filtered = useMemo(() => {
    const list = data ?? [];
    if (!search.trim()) return list;
    const term = search.toLowerCase();
    return list.filter((dataset) => dataset.name.toLowerCase().includes(term) || (dataset.file_name ?? "").toLowerCase().includes(term));
  }, [data, search]);

  const loadDemo = async () => {
    if (!workspaceId) return;
    setDemoLoading(true);
    try {
      const result = await api.post<{ dataset_id: string; job_id: string }>("/datasets/demo", { workspace_id: workspaceId });
      toast.info("Generating synthetic retail dataset…");
      for (let i = 0; i < 120; i += 1) {
        const job = await api.get<Job>(`/jobs/${result.job_id}`);
        if (job.status === "completed") {
          toast.success("Demo dataset ready");
          router.push(`/app/datasets/${result.dataset_id}`);
          return;
        }
        if (job.status === "failed") throw new Error(job.error || "Processing failed");
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Data"
        title="Datasets"
        description="Every upload is validated, profiled and versioned. Original files are preserved; cleaning is proposed, never silently applied."
        actions={
          <>
            <Button variant="outline" onClick={loadDemo} loading={demoLoading}>
              <Wand2 className="h-4 w-4" /> Retail demo
            </Button>
            {workspaceId && <UploadDatasetDialog workspaceId={workspaceId} onUploaded={refresh} />}
          </>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
          <Input placeholder="Search datasets…" value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" />
        </div>
        <p className="text-[12px] text-muted">{filtered.length} dataset{filtered.length === 1 ? "" : "s"}</p>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => <div key={i} className="glass rounded-2xl p-5"><Skeleton className="h-4 w-40" /><Skeleton className="mt-4 h-8 w-24" /><Skeleton className="mt-4 h-3 w-full" /></div>)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass rounded-2xl">
          <EmptyState
            icon={Database}
            title={search ? "No datasets match that search" : "Your first dataset is one upload away"}
            description={
              search
                ? "Try a different name or clear the search."
                : "Upload a CSV or Excel workbook, or load the deterministic synthetic retail dataset to explore dashboards and the AI analyst immediately."
            }
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="gradient" onClick={loadDemo} loading={demoLoading}>
                  <Sparkles className="h-4 w-4" /> Load retail demo
                </Button>
                {workspaceId && <UploadDatasetDialog workspaceId={workspaceId} onUploaded={refresh} trigger={<Button variant="outline">Upload a file</Button>} />}
              </div>
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((dataset) => {
            const quality = qualityTone(dataset.quality_score);
            const processing = dataset.status === "processing";
            return (
              <Link
                key={dataset.id}
                href={`/app/datasets/${dataset.id}`}
                className="glass glass-hover group flex flex-col rounded-2xl p-5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/10 text-brand">
                    <Database className="h-[18px] w-[18px]" strokeWidth={1.7} />
                  </span>
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {dataset.is_synthetic && <Badge tone="violet">Synthetic</Badge>}
                    <Badge tone={processing ? "warning" : dataset.status === "failed" ? "danger" : "success"}>
                      {processing ? "Processing" : dataset.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                </div>

                <h3 className="mt-4 truncate font-display text-[15px] font-semibold text-ink">{dataset.name}</h3>
                <p className="mt-1 flex items-center gap-1.5 truncate text-[11.5px] text-muted">
                  <FileSpreadsheet className="h-3 w-3" /> {dataset.file_name ?? "uploaded file"}
                </p>

                <div className="mt-4 grid grid-cols-3 gap-2 rounded-xl border border-line/10 bg-line/[0.02] p-2.5">
                  <div>
                    <p className="text-[9.5px] uppercase tracking-[0.1em] text-faint">Rows</p>
                    <p className="kpi-value mt-0.5 text-[14px] font-semibold text-ink">{dataset.row_count.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-[9.5px] uppercase tracking-[0.1em] text-faint">Columns</p>
                    <p className="kpi-value mt-0.5 text-[14px] font-semibold text-ink">{dataset.column_count}</p>
                  </div>
                  <div>
                    <p className="text-[9.5px] uppercase tracking-[0.1em] text-faint">Quality</p>
                    <p className="kpi-value mt-0.5 text-[14px] font-semibold text-ink">
                      {dataset.quality_score ?? "—"}
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between text-[11.5px] text-muted">
                  <span className="flex items-center gap-1.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${quality.tone === "success" ? "bg-success" : quality.tone === "warning" ? "bg-warning" : quality.tone === "danger" ? "bg-danger" : "bg-brand"}`} />
                    {quality.label}
                  </span>
                  <span>{relativeTime(dataset.created_at)}</span>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-line/10 pt-3">
                  <span className="text-[11.5px] text-muted">
                    {dataset.semantic_status === "approved" ? "Semantic model approved" : dataset.semantic_status === "proposed" ? "Semantic review pending" : "No semantic model"}
                  </span>
                  <ArrowUpRight className="h-4 w-4 text-faint transition group-hover:text-brand" />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
