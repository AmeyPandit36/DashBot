"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Activity, ArrowRight, ArrowUpRight, BarChart3, Bot, Database, FileSpreadsheet,
  Lightbulb, Loader2, MessageSquare, Plus, Sparkles, Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SkeletonCard } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { UploadDatasetDialog } from "@/components/dashboard/upload-dialog";
import { formatDate, qualityTone, relativeTime } from "@/lib/format";
import type { Conversation, DashboardSummary, Dataset, Insight, Job } from "@/lib/types";

interface WorkspaceDetail {
  id: string;
  name: string;
  description?: string;
  recent_datasets: Dataset[];
  recent_dashboards: DashboardSummary[];
  recent_conversations: Conversation[];
}

const SUGGESTIONS = [
  "What is total revenue?",
  "Which region performs best?",
  "Why did revenue decrease recently?",
  "What are the major business insights?",
];

export default function OverviewPage() {
  const { session, workspace } = useAuth();
  const router = useRouter();
  const [loadingDemo, setLoadingDemo] = useState(false);

  const workspaceId = workspace?.id;
  const detail = useApi<WorkspaceDetail>(workspaceId ? `/workspaces/${workspaceId}` : null);
  const datasets = useApi<Dataset[]>(workspaceId ? `/datasets?workspace_id=${workspaceId}` : null);
  const dashboards = useApi<DashboardSummary[]>(workspaceId ? `/dashboards?workspace_id=${workspaceId}` : null);
  const insights = useApi<Insight[]>(workspaceId ? `/insights?workspace_id=${workspaceId}` : null);

  const datasetList = datasets.data ?? [];
  const readyDatasets = datasetList.filter((d) => d.status === "ready" || d.status === "needs_review");
  const avgQuality = readyDatasets.length
    ? Math.round(readyDatasets.reduce((sum, d) => sum + (d.quality_score ?? 0), 0) / readyDatasets.length)
    : null;

  const loadDemo = async () => {
    if (!workspaceId) return;
    setLoadingDemo(true);
    try {
      const result = await api.post<{ dataset_id: string; job_id: string }>("/datasets/demo", { workspace_id: workspaceId });
      toast.info("Synthetic retail dataset queued", { description: "Profiling and semantic inference running…" });
      for (let i = 0; i < 120; i += 1) {
        const job = await api.get<Job>(`/jobs/${result.job_id}`);
        if (job.status === "completed") {
          toast.success("Demo dataset ready", { description: "Review the semantic model, then generate a dashboard." });
          router.push(`/app/datasets/${result.dataset_id}`);
          return;
        }
        if (job.status === "failed") throw new Error(job.error || "Processing failed");
        await new Promise((resolve) => setTimeout(resolve, 800));
      }
      throw new Error("Processing is taking longer than expected. Check the dataset list shortly.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setLoadingDemo(false);
    }
  };

  const firstName = session?.user.full_name?.split(" ")[0] || "there";

  return (
    <div className="space-y-7">
      <PageHeader
        eyebrow={workspace?.name}
        title={`Welcome back, ${firstName}`}
        description="Your analytical workspace: profile data, approve the semantic model, then interrogate performance with verified answers."
        actions={
          <>
            <Button variant="outline" onClick={loadDemo} loading={loadingDemo}>
              <Wand2 className="h-4 w-4" /> Load retail demo
            </Button>
            {workspaceId && <UploadDatasetDialog workspaceId={workspaceId} />}
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Datasets" value={readyDatasets.length || "—"} icon={Database} tone="brand"
          hint={datasetList.length ? `${datasetList.length} uploaded in total` : "No datasets yet"} loading={datasets.loading} />
        <StatCard label="Dashboards" value={dashboards.data?.length ?? "—"} icon={BarChart3} tone="violet"
          hint={dashboards.data?.some((d) => d.status === "published") ? "Published and versioned" : "Generate from a semantic model"}
          loading={dashboards.loading} />
        <StatCard label="AI conversations" value={detail.data?.recent_conversations.length ?? "—"} icon={MessageSquare} tone="cyan"
          hint="Every answer carries SQL provenance" loading={detail.loading} />
        <StatCard label="Avg. data quality" value={avgQuality !== null ? `${avgQuality}/100` : "—"} icon={Sparkles} tone="teal"
          hint="Deterministic, documented formula" loading={datasets.loading} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.55fr_1fr]">
        <div className="space-y-5">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-[15px] font-semibold text-ink">Recent datasets</h2>
                <p className="mt-0.5 text-[12px] text-muted">Profiled files, semantic status and analytical readiness.</p>
              </div>
              <Button asChild variant="ghost" size="sm">
                <Link href="/app/datasets">View all <ArrowRight className="h-3.5 w-3.5" /></Link>
              </Button>
            </div>

            <div className="mt-4 space-y-2">
              {datasets.loading && [0, 1, 2].map((i) => <div key={i} className="h-16 skeleton rounded-xl" />)}
              {!datasets.loading && datasetList.length === 0 && (
                <EmptyState
                  icon={FileSpreadsheet}
                  compact
                  title="No datasets yet"
                  description="Load the synthetic retail demo to explore the full workflow, or upload your own CSV/XLSX file."
                  action={
                    <div className="flex gap-2">
                      <Button size="sm" variant="gradient" onClick={loadDemo} loading={loadingDemo}>
                        <Wand2 className="h-3.5 w-3.5" /> Load demo data
                      </Button>
                      {workspaceId && <UploadDatasetDialog workspaceId={workspaceId} trigger={<Button size="sm" variant="outline">Upload file</Button>} />}
                    </div>
                  }
                />
              )}
              {datasetList.slice(0, 5).map((dataset) => {
                const quality = qualityTone(dataset.quality_score);
                return (
                  <Link
                    key={dataset.id}
                    href={`/app/datasets/${dataset.id}`}
                    className="group flex items-center gap-3 rounded-xl border border-line/10 bg-line/[0.02] px-3.5 py-3 transition hover:border-brand/30 hover:bg-brand/[0.03]"
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
                      <Database className="h-4 w-4" strokeWidth={1.7} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-[13.5px] font-medium text-ink">{dataset.name}</p>
                        {dataset.is_synthetic && <Badge tone="violet">Synthetic</Badge>}
                      </div>
                      <p className="mt-0.5 text-[11.5px] text-muted">
                        {dataset.row_count.toLocaleString()} rows · {dataset.column_count} columns · v{dataset.active_version}
                        {" · "}{relativeTime(dataset.created_at)}
                      </p>
                    </div>
                    <div className="hidden items-center gap-2 sm:flex">
                      {dataset.semantic_status === "approved" ? (
                        <Badge tone="success">Model approved</Badge>
                      ) : dataset.semantic_status === "proposed" ? (
                        <Badge tone="warning">Review model</Badge>
                      ) : (
                        <Badge tone="neutral">No model</Badge>
                      )}
                      <Badge tone={quality.tone}>{dataset.quality_score ?? "—"} quality</Badge>
                    </div>
                    <ArrowUpRight className="h-4 w-4 shrink-0 text-faint transition group-hover:text-brand" />
                  </Link>
                );
              })}
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-[15px] font-semibold text-ink">Dashboards</h2>
                <p className="mt-0.5 text-[12px] text-muted">Generated from approved semantic models.</p>
              </div>
              <Button asChild variant="ghost" size="sm">
                <Link href="/app/dashboards">All dashboards <ArrowRight className="h-3.5 w-3.5" /></Link>
              </Button>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {dashboards.loading && [0, 1].map((i) => <SkeletonCard key={i} className="h-[120px]" />)}
              {!dashboards.loading && (dashboards.data ?? []).length === 0 && (
                <div className="sm:col-span-2">
                  <EmptyState
                    icon={BarChart3}
                    compact
                    title="No dashboards yet"
                    description="Approve a semantic model to generate an interactive dashboard specification."
                    action={<Button asChild size="sm" variant="outline"><Link href="/app/datasets">Go to datasets</Link></Button>}
                  />
                </div>
              )}
              {(dashboards.data ?? []).slice(0, 4).map((dashboard) => (
                <Link
                  key={dashboard.id}
                  href={`/app/dashboards/${dashboard.id}`}
                  className="group rounded-xl border border-line/10 bg-gradient-to-br from-brand/[0.06] to-violet/[0.03] p-4 transition hover:border-brand/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">{dashboard.title}</p>
                    <Badge tone={dashboard.status === "published" ? "success" : "warning"}>
                      {dashboard.status}
                    </Badge>
                  </div>
                  <p className="mt-2 text-[11.5px] text-muted">
                    {dashboard.widget_count} widgets · v{dashboard.version} · {dashboard.generation_mode} mode
                  </p>
                  <p className="mt-3 flex items-center gap-1 text-[11px] font-medium text-brand opacity-0 transition group-hover:opacity-100">
                    Open dashboard <ArrowRight className="h-3 w-3" />
                  </p>
                </Link>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="overflow-hidden">
            <div className="border-b border-line/10 bg-gradient-to-br from-brand/[0.12] via-violet/[0.06] to-transparent p-5">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient text-white">
                  <Bot className="h-4 w-4" />
                </span>
                <div>
                  <h2 className="font-display text-[14px] font-semibold text-ink">Ask the AI analyst</h2>
                  <p className="text-[11px] text-muted">Answers computed by SQL, verified against evidence</p>
                </div>
              </div>
              <div className="mt-4 space-y-1.5">
                {SUGGESTIONS.map((question) => (
                  <Link
                    key={question}
                    href={`/app/analyst?q=${encodeURIComponent(question)}`}
                    className="flex items-center justify-between gap-2 rounded-lg border border-line/10 bg-surface/60 px-3 py-2 text-[12px] text-muted transition hover:border-brand/30 hover:text-ink"
                  >
                    {question}
                    <ArrowRight className="h-3 w-3 shrink-0" />
                  </Link>
                ))}
              </div>
              <Button asChild variant="gradient" size="sm" className="mt-3 w-full">
                <Link href="/app/analyst"><MessageSquare className="h-3.5 w-3.5" /> Open analyst</Link>
              </Button>
            </div>
            <div className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">Recent conversations</p>
                <MessageSquare className="h-3.5 w-3.5 text-faint" />
              </div>
              <div className="mt-3 space-y-1">
                {(detail.data?.recent_conversations ?? []).slice(0, 4).map((conversation) => (
                  <Link
                    key={conversation.id}
                    href={`/app/analyst?c=${conversation.id}`}
                    className="block truncate rounded-lg px-2 py-1.5 text-[12px] text-muted transition hover:bg-line/[0.05] hover:text-ink"
                  >
                    {conversation.title}
                  </Link>
                ))}
                {(detail.data?.recent_conversations ?? []).length === 0 && (
                  <p className="px-2 py-2 text-[12px] text-faint">No questions asked yet.</p>
                )}
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-[14px] font-semibold text-ink">Latest insights</h2>
              <Button asChild variant="ghost" size="sm">
                <Link href="/app/insights">View all</Link>
              </Button>
            </div>
            <div className="mt-3 space-y-2.5">
              {insights.loading && [0, 1].map((i) => <div key={i} className="h-14 skeleton rounded-lg" />)}
              {(insights.data ?? []).slice(0, 3).map((insight) => (
                <div key={insight.id} className="rounded-lg border border-line/10 bg-line/[0.02] p-3">
                  <div className="flex items-start gap-2">
                    <Lightbulb className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${insight.severity === "critical" ? "text-danger" : insight.severity === "positive" ? "text-success" : "text-warning"}`} />
                    <p className="text-[12px] font-medium leading-snug text-ink">{insight.title}</p>
                  </div>
                  <p className="mt-1.5 line-clamp-2 pl-5 text-[11.5px] leading-relaxed text-muted">{insight.summary}</p>
                </div>
              ))}
              {!insights.loading && (insights.data ?? []).length === 0 && (
                <p className="text-[12px] text-faint">Generate insights from a dataset to populate this feed.</p>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center gap-2">
              <Activity className="h-3.5 w-3.5 text-cyan" />
              <h2 className="font-display text-[14px] font-semibold text-ink">Activity</h2>
            </div>
            <div className="mt-3 space-y-2">
              {(detail.data?.recent_datasets ?? []).slice(0, 2).map((dataset) => (
                <div key={dataset.id} className="flex items-start gap-2 text-[11.5px] text-muted">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/60" />
                  <span><span className="text-ink">{dataset.name}</span> ingested · {formatDate(dataset.created_at)}</span>
                </div>
              ))}
              {(detail.data?.recent_dashboards ?? []).slice(0, 1).map((dashboard) => (
                <div key={dashboard.id} className="flex items-start gap-2 text-[11.5px] text-muted">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet/60" />
                  <span><span className="text-ink">{dashboard.title}</span> dashboard updated · {relativeTime(dashboard.updated_at)}</span>
                </div>
              ))}
              {!detail.loading && (detail.data?.recent_datasets ?? []).length === 0 && (
                <p className="text-[11.5px] text-faint">No activity recorded yet.</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
