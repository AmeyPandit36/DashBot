"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, ArrowUpRight, BadgeCheck, Bot, CheckCircle2, Info, Lightbulb, RefreshCw, Sparkles, TrendingDown, TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SQLViewer } from "@/components/common/sql-viewer";
import { VerificationBadge } from "@/components/common/verification-badge";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, relativeTime, titleCase } from "@/lib/format";
import type { Dataset, Insight } from "@/lib/types";

const SEVERITY = {
  positive: { icon: TrendingUp, tone: "success" as const, ring: "border-success/25 bg-success/[0.06]", chip: "text-success" },
  warning: { icon: AlertTriangle, tone: "warning" as const, ring: "border-warning/25 bg-warning/[0.06]", chip: "text-warning" },
  critical: { icon: TrendingDown, tone: "danger" as const, ring: "border-danger/25 bg-danger/[0.06]", chip: "text-danger" },
  info: { icon: Info, tone: "brand" as const, ring: "border-brand/20 bg-brand/[0.04]", chip: "text-brand" },
};

export default function InsightsPage() {
  const { workspace } = useAuth();
  const workspaceId = workspace?.id;
  const datasets = useApi<Dataset[]>(workspaceId ? `/datasets?workspace_id=${workspaceId}` : null);
  const [datasetFilter, setDatasetFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const insights = useApi<Insight[]>(
    workspaceId
      ? `/insights?workspace_id=${workspaceId}${datasetFilter !== "all" ? `&dataset_id=${datasetFilter}` : ""}`
      : null,
  );
  const [generating, setGenerating] = useState(false);

  const datasetNames = useMemo(
    () => new Map((datasets.data ?? []).map((dataset) => [dataset.id, dataset.name])),
    [datasets.data],
  );

  const visible = useMemo(() => {
    const list = insights.data ?? [];
    return severityFilter === "all" ? list : list.filter((insight) => insight.severity === severityFilter);
  }, [insights.data, severityFilter]);

  const generate = async () => {
    const target = datasetFilter !== "all" ? datasetFilter : datasets.data?.[0]?.id;
    if (!target) {
      toast.error("Add a dataset before generating insights");
      return;
    }
    setGenerating(true);
    try {
      const result = await api.post<Insight[]>("/insights/generate", { dataset_id: target });
      toast.success(`${result.length} insights generated`, { description: "Each finding is backed by an executed query." });
      void insights.refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Monitor"
        title="Insights"
        description="Automated findings from your datasets — every claim is generated from executed SQL and checked by the verifier agent."
        actions={
          <Button variant="gradient" onClick={generate} loading={generating}>
            <Sparkles className="h-4 w-4" /> Generate insights
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-[220px]">
          <Select value={datasetFilter} onValueChange={setDatasetFilter}>
            <SelectTrigger className="h-9 text-[12px]"><SelectValue placeholder="All datasets" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All datasets</SelectItem>
              {(datasets.data ?? []).map((dataset) => <SelectItem key={dataset.id} value={dataset.id}>{dataset.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="w-[170px]">
          <Select value={severityFilter} onValueChange={setSeverityFilter}>
            <SelectTrigger className="h-9 text-[12px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All severities</SelectItem>
              {["positive", "warning", "critical", "info"].map((severity) => (
                <SelectItem key={severity} value={severity}>{titleCase(severity)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <span className="text-[11.5px] text-faint">{visible.length} findings</span>
        <Button variant="ghost" size="sm" onClick={() => void insights.refresh()} className="ml-auto">
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {insights.loading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((index) => <div key={index} className="glass rounded-2xl p-5"><Skeleton className="h-4 w-48" /><Skeleton className="mt-3 h-3 w-full" /><Skeleton className="mt-2 h-3 w-2/3" /></div>)}
        </div>
      ) : visible.length === 0 ? (
        <div className="glass rounded-2xl">
          <EmptyState
            icon={Lightbulb}
            title="No insights yet"
            description="Run the insight generator to scan trends, concentration, data quality and anomalies. Findings are verified before they appear here."
            action={<Button variant="gradient" onClick={generate} loading={generating}><Sparkles className="h-4 w-4" /> Generate insights</Button>}
          />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {visible.map((insight) => {
            const config = SEVERITY[insight.severity as keyof typeof SEVERITY] ?? SEVERITY.info;
            const Icon = config.icon;
            const evidence = insight.evidence as { sql?: string; metric?: string; change_pct?: number } | null;
            return (
              <article key={insight.id} className={`glass flex flex-col rounded-2xl border p-5 ${config.ring}`}>
                <div className="flex items-start gap-3">
                  <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface/70 ${config.chip}`}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={config.tone}>{titleCase(insight.insight_type)}</Badge>
                      {insight.verified && <span className="flex items-center gap-0.5 text-[10.5px] font-medium text-success"><BadgeCheck className="h-3 w-3" /> verified</span>}
                    </div>
                    <h3 className="mt-1.5 font-display text-[14.5px] font-semibold leading-snug text-ink">{insight.title}</h3>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-muted">{insight.summary}</p>
                  </div>
                </div>

                {evidence?.sql && (
                  <div className="mt-3">
                    <SQLViewer sql={evidence.sql} label="Evidence query" />
                  </div>
                )}

                <div className="mt-auto flex items-center justify-between gap-2 border-t border-line/10 pt-3 text-[11px] text-faint">
                  <span className="truncate">
                    {insight.dataset_id ? datasetNames.get(insight.dataset_id) ?? "Dataset" : "Workspace"} · {relativeTime(insight.created_at)}
                  </span>
                  <div className="flex items-center gap-2">
                    <VerificationBadge status={insight.verified ? "verified" : "unverified"} />
                    {insight.dataset_id && (
                      <Link href={`/app/analyst?datasetId=${insight.dataset_id}`} className="flex items-center gap-0.5 font-medium text-brand hover:underline">
                        Investigate <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <div className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand/20 to-violet/10 text-brand">
            <Bot className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[12.5px] font-medium text-ink">How insights are produced</p>
            <p className="text-[11.5px] text-muted">Deterministic scans over real aggregates, then the critic agent re-runs every number before publishing.</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted">
          <CheckCircle2 className="h-3.5 w-3.5 text-success" /> provenance kept for every finding
        </div>
      </div>
    </div>
  );
}
