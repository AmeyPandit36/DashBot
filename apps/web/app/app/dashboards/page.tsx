"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, BarChart3, Plus, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { DashboardSummary, Dataset } from "@/lib/types";

export default function DashboardsPage() {
  const { workspace } = useAuth();
  const router = useRouter();
  const workspaceId = workspace?.id;
  const dashboards = useApi<DashboardSummary[]>(workspaceId ? `/dashboards?workspace_id=${workspaceId}` : null);
  const datasets = useApi<Dataset[]>(workspaceId ? `/datasets?workspace_id=${workspaceId}` : null);
  const [datasetChoice, setDatasetChoice] = useState<string>("");
  const [mode, setMode] = useState<"review" | "automatic">("review");
  const [generating, setGenerating] = useState(false);
  const [open, setOpen] = useState(false);

  const datasetMap = useMemo(
    () => new Map((datasets.data ?? []).map((dataset) => [dataset.id, dataset])),
    [datasets.data],
  );
  const eligible = (datasets.data ?? []).filter((dataset) => dataset.semantic_status === "approved");

  const generate = async () => {
    if (!datasetChoice) {
      toast.error("Select a dataset with an approved semantic model");
      return;
    }
    setGenerating(true);
    try {
      const result = await api.post<{ id: string }>("/dashboards/generate", {
        dataset_id: datasetChoice,
        mode,
      });
      toast.success(mode === "automatic" ? "Dashboard published" : "Dashboard draft generated", {
        description: mode === "automatic" ? "Rendering the approved specification." : "Review the widgets, then publish.",
      });
      setOpen(false);
      router.push(`/app/dashboards/${result.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Visualise"
        title="Dashboards"
        description="Declarative specifications rendered by a trusted component registry. Charts and tables execute real SQL against the dataset version."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button variant="gradient"><Plus className="h-4 w-4" /> New dashboard</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Generate a dashboard</DialogTitle>
                <DialogDescription>
                  The planner uses the approved semantic model. Review mode creates a draft you can edit before
                  publishing; automatic mode publishes immediately.
                </DialogDescription>
              </DialogHeader>
              <div className="mt-5 space-y-4">
                <div className="space-y-1.5">
                  <Label>Dataset</Label>
                  <Select value={datasetChoice} onValueChange={setDatasetChoice}>
                    <SelectTrigger><SelectValue placeholder={eligible.length ? "Choose a dataset" : "No approved semantic models"} /></SelectTrigger>
                    <SelectContent>
                      {eligible.map((dataset) => (
                        <SelectItem key={dataset.id} value={dataset.id}>{dataset.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {eligible.length === 0 && (
                    <p className="text-[11.5px] text-muted">
                      Approve a semantic model first — <Link href="/app/datasets" className="font-medium text-brand hover:underline">go to datasets</Link>.
                    </p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label>Generation mode</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {(["review", "automatic"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setMode(option)}
                        className={`rounded-xl border p-3 text-left transition ${mode === option ? "border-brand/50 bg-brand/[0.06]" : "border-line/12 hover:border-line/25"}`}
                      >
                        <p className="text-[12.5px] font-medium text-ink capitalize">{option}</p>
                        <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                          {option === "review" ? "Preview and edit, then publish." : "Generate and publish in one step."}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
                <Button className="w-full" variant="gradient" onClick={generate} loading={generating} disabled={!eligible.length}>
                  <Sparkles className="h-4 w-4" /> Generate dashboard
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        }
      />

      {dashboards.loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => <Card key={i} className="p-5"><Skeleton className="h-4 w-40" /><Skeleton className="mt-4 h-3 w-28" /></Card>)}
        </div>
      ) : (dashboards.data ?? []).length === 0 ? (
        <div className="glass rounded-2xl">
          <EmptyState
            icon={BarChart3}
            title="No dashboards yet"
            description="Approve a semantic model and the planner will propose KPI cards, trends, breakdowns and a detail table — all validated against a strict schema."
            action={<Button variant="gradient" onClick={() => setOpen(true)}><Sparkles className="h-4 w-4" /> Generate a dashboard</Button>}
          />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {(dashboards.data ?? []).map((dashboard) => {
            const dataset = datasetMap.get(dashboard.dataset_id);
            return (
              <Link key={dashboard.id} href={`/app/dashboards/${dashboard.id}`} className="glass glass-hover group flex flex-col rounded-2xl p-5">
                <div className="flex items-start justify-between gap-2">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand/20 to-violet/10 text-brand">
                    <BarChart3 className="h-4 w-4" />
                  </span>
                  <Badge tone={dashboard.status === "published" ? "success" : "warning"}>{dashboard.status}</Badge>
                </div>
                <h3 className="mt-4 font-display text-[15px] font-semibold text-ink">{dashboard.title}</h3>
                <p className="mt-1 text-[11.5px] text-muted">
                  {dataset?.name ?? "Dataset"} · {dashboard.widget_count} widgets · v{dashboard.version}
                </p>
                <div className="mt-4 flex items-center justify-between border-t border-line/10 pt-3 text-[11px] text-muted">
                  <span>{dashboard.generation_mode} generation</span>
                  <span className="flex items-center gap-1 font-medium text-brand opacity-0 transition group-hover:opacity-100">
                    Open <ArrowUpRight className="h-3.5 w-3.5" />
                  </span>
                </div>
                <p className="mt-1 text-[10.5px] text-faint">Updated {relativeTime(dashboard.updated_at)}</p>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
