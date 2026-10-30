"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle, ArrowLeft, ArrowUpRight, BarChart3, CheckCircle2, Columns3, Database,
  FileText, Layers, Sparkles, Table2, Trash2, Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/common/stat-card";
import { EmptyState } from "@/components/common/empty-state";
import { DataTable } from "@/components/common/data-table";
import { PageSkeleton, InlineLoader } from "@/components/common/loading";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatNumber, qualityTone } from "@/lib/format";
import type { Dataset, DatasetVersion, Profile, SemanticModel } from "@/lib/types";
import type { ColumnDef } from "@tanstack/react-table";

interface PreviewData {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  preview_rows: number;
}

interface SchemaData {
  table_name: string;
  columns: { name: string; type: string; nullable: boolean; unique_count: number; null_pct: number }[];
}

function QualityDial({ score }: { score: number }) {
  const color = score >= 90 ? "#10B981" : score >= 75 ? "#4F6BFF" : score >= 60 ? "#F59E0B" : "#F43F5E";
  return (
    <div
      className="relative flex h-24 w-24 items-center justify-center rounded-full"
      style={{ background: `conic-gradient(${color} ${score * 3.6}deg, rgba(120,130,160,0.16) 0deg)` }}
      role="img"
      aria-label={`Data quality score ${score} out of 100`}
    >
      <div className="flex h-[76px] w-[76px] flex-col items-center justify-center rounded-full bg-surface">
        <span className="kpi-value text-xl font-semibold text-ink">{score.toFixed(1)}</span>
        <span className="text-[9px] uppercase tracking-[0.12em] text-faint">of 100</span>
      </div>
    </div>
  );
}

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const datasetId = params.id;
  const router = useRouter();
  const dataset = useApi<Dataset>(`/datasets/${datasetId}`);
  const profile = useApi<{ profile: Profile; cleaning_plan: Profile["cleaning_plan"] }>(`/datasets/${datasetId}/profile`);
  const preview = useApi<PreviewData>(`/datasets/${datasetId}/preview?limit=25`);
  const schema = useApi<SchemaData>(`/datasets/${datasetId}/schema`);
  const versions = useApi<DatasetVersion[]>(`/datasets/${datasetId}/versions`);
  const semantic = useApi<SemanticModel>(`/semantic-models/dataset/${datasetId}`);

  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedOps, setSelectedOps] = useState<string[]>([]);

  const previewColumns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    if (!preview.data) return [];
    return preview.data.columns.map((column) => ({
      accessorKey: column,
      header: column.replace(/_/g, " "),
      cell: ({ getValue }) => {
        const value = getValue();
        if (value === null || value === undefined) return <span className="text-faint">null</span>;
        if (typeof value === "number") return <span className="font-mono tabular-nums">{formatNumber(value)}</span>;
        const text = String(value);
        return <span title={text}>{text.length > 40 ? `${text.slice(0, 39)}…` : text}</span>;
      },
    }));
  }, [preview.data]);

  const generateDashboard = async () => {
    setBusyAction("dashboard");
    try {
      const result = await api.post<{ id: string }>("/dashboards/generate", { dataset_id: datasetId, mode: "automatic" });
      toast.success("Dashboard generated");
      router.push(`/app/dashboards/${result.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyAction(null);
    }
  };

  const runClean = async () => {
    if (!selectedOps.length) return;
    setBusyAction("clean");
    try {
      await api.post(`/datasets/${datasetId}/clean`, { operations: selectedOps });
      toast.success("New dataset version created", { description: "The semantic model was regenerated for review." });
      setSelectedOps([]);
      profile.refresh();
      versions.refresh();
      dataset.refresh();
      semantic.refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyAction(null);
    }
  };

  const deleteDataset = async () => {
    setBusyAction("delete");
    try {
      await api.del(`/datasets/${datasetId}`);
      toast.success("Dataset deleted");
      router.push("/app/datasets");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusyAction(null);
    }
  };

  if (dataset.loading) return <PageSkeleton />;
  if (dataset.error || !dataset.data) {
    return (
      <div className="glass rounded-2xl">
        <EmptyState
          icon={Database}
          title="Dataset not available"
          description={dataset.error || "This dataset may have been deleted."}
          action={<Button asChild variant="outline"><Link href="/app/datasets"><ArrowLeft className="h-4 w-4" /> Back to datasets</Link></Button>}
        />
      </div>
    );
  }

  const data = dataset.data;
  const prof = profile.data?.profile;
  const quality = qualityTone(data.quality_score);
  const hasSemantic = Boolean(semantic.data);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <Link href="/app/datasets" className="inline-flex items-center gap-1 transition hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> Datasets
        </Link>
        <span className="text-faint">/</span>
        <span className="text-ink">{data.name}</span>
      </div>

      <PageHeader
        eyebrow={`${data.row_count.toLocaleString()} rows · ${data.column_count} columns · v${data.active_version}`}
        title={data.name}
        description={data.description || "Profiled dataset with an approved or proposed semantic model, ready for dashboards and conversational analysis."}
        actions={
          <>
            {hasSemantic ? (
              <Button asChild variant="outline">
                <Link href={`/app/semantic/${datasetId}`}>
                  <Layers className="h-4 w-4" /> {semantic.data?.status === "approved" ? "Semantic model" : "Review semantic model"}
                </Link>
              </Button>
            ) : (
              <Button
                variant="outline"
                loading={busyAction === "semantic"}
                onClick={async () => {
                  setBusyAction("semantic");
                  try {
                    await api.post("/semantic-models/generate", { dataset_id: datasetId });
                    toast.success("Semantic model proposed");
                    semantic.refresh();
                  } catch (err) {
                    toast.error(errorMessage(err));
                  } finally {
                    setBusyAction(null);
                  }
                }}
              >
                <Sparkles className="h-4 w-4" /> Generate model
              </Button>
            )}
            <Button variant="gradient" onClick={generateDashboard} loading={busyAction === "dashboard"} disabled={!hasSemantic || semantic.data?.status !== "approved"}>
              <BarChart3 className="h-4 w-4" /> Generate dashboard
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Dataset actions"><Trash2 className="h-4 w-4" /></Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete this dataset?</DialogTitle>
                  <DialogDescription>
                    This removes the dataset, its versions, semantic models and dashboards. Conversations keep their
                    history but query provenance will point to a deleted dataset.
                  </DialogDescription>
                </DialogHeader>
                <div className="mt-5 flex justify-end gap-2">
                  <Button variant="outline">Cancel</Button>
                  <Button variant="destructive" onClick={deleteDataset} loading={busyAction === "delete"}>Delete dataset</Button>
                </div>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={data.status === "ready" ? "success" : data.status === "needs_review" ? "warning" : "neutral"}>
          {data.status.replace(/_/g, " ")}
        </Badge>
        {data.is_synthetic && <Badge tone="violet">Synthetic demonstration data</Badge>}
        <Badge tone={quality.tone}>{quality.label} quality</Badge>
        {semantic.data && (
          <Badge tone={semantic.data.status === "approved" ? "success" : "warning"}>
            Semantic v{semantic.data.version} · {semantic.data.status}
          </Badge>
        )}
        <span className="text-[11.5px] text-faint">Uploaded {formatDate(data.created_at, { month: "short", day: "numeric", year: "numeric" })}</span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Rows" value={data.row_count.toLocaleString()} icon={Table2} tone="brand" hint={`${data.column_count} columns`} />
        <StatCard label="Quality score" value={prof ? `${prof.quality_score}/100` : "—"} icon={CheckCircle2} tone="teal" hint={prof ? `${prof.completeness_pct}% complete` : "Profiling…"} />
        <StatCard label="Missing cells" value={prof ? prof.missing_cells.toLocaleString() : "—"} icon={AlertTriangle} tone="warning" hint={prof ? `${prof.duplicate_rows} duplicate rows` : ""} />
        <StatCard label="Versions" value={data.version_count} icon={Layers} tone="violet" hint={`Active v${data.active_version}`} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="profile">Data profile</TabsTrigger>
          <TabsTrigger value="schema">Schema</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
            <Card className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-display text-[15px] font-semibold text-ink">Quality breakdown</h2>
                  <p className="mt-0.5 text-[12px] text-muted">Deterministic weighted score — every component is measurable.</p>
                </div>
                {prof && <QualityDial score={prof.quality_score} />}
              </div>
              <div className="mt-5 space-y-3">
                {prof ? (
                  Object.entries(prof.quality_components).map(([key, value]) => (
                    <div key={key}>
                      <div className="flex items-center justify-between text-[12px]">
                        <span className="capitalize text-muted">{key.replace(/_/g, " ")}</span>
                        <span className="font-mono text-[11.5px] text-ink">{(value * 100).toFixed(1)}%</span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line/10">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-brand to-violet"
                          style={{ width: `${Math.max(2, value * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))
                ) : (
                  <InlineLoader label="Computing profile" />
                )}
              </div>
              {prof && (
                <details className="mt-4 rounded-lg border border-line/10 bg-line/[0.02] p-3">
                  <summary className="cursor-pointer text-[11.5px] font-medium text-muted">How this score is calculated</summary>
                  <p className="mt-2 font-mono text-[10.5px] leading-relaxed text-faint">{prof.quality_formula.expression}</p>
                  <ul className="mt-2 space-y-1">
                    {Object.entries(prof.quality_formula.definitions).map(([key, definition]) => (
                      <li key={key} className="text-[11px] leading-relaxed text-muted">
                        <span className="font-medium text-ink">{key.replace(/_/g, " ")}</span> — {definition}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-[15px] font-semibold text-ink">Cleaning recommendations</h2>
                <Badge tone="neutral">{profile.data?.profile.recommendations.length ?? 0}</Badge>
              </div>
              <p className="mt-0.5 text-[12px] text-muted">Opt-in operations. Nothing is applied without your approval.</p>
              <div className="mt-4 space-y-2">
                {(profile.data?.profile.recommendations ?? []).map((rec) => (
                  <div key={rec.id} className="rounded-xl border border-line/10 bg-line/[0.02] p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[12.5px] font-medium text-ink">{rec.title}</p>
                      <Badge tone={rec.impact === "high" ? "danger" : rec.impact === "medium" ? "warning" : "neutral"}>{rec.impact}</Badge>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{rec.detail}</p>
                    {["drop_duplicates", "trim_whitespace"].includes(rec.action) && (
                      <label className="mt-2 flex cursor-pointer items-center gap-2 text-[11.5px] text-muted">
                        <input
                          type="checkbox"
                          checked={selectedOps.includes(rec.action)}
                          onChange={(event) =>
                            setSelectedOps((current) =>
                              event.target.checked ? [...current, rec.action] : current.filter((op) => op !== rec.action),
                            )
                          }
                          className="h-3.5 w-3.5 rounded border-line/30 accent-[#4F6BFF]"
                        />
                        Include in new version
                      </label>
                    )}
                  </div>
                ))}
                {!profile.loading && (profile.data?.profile.recommendations.length ?? 0) === 0 && (
                  <p className="rounded-xl border border-success/20 bg-success/[0.05] p-3 text-[12px] text-success">
                    No cleaning issues detected.
                  </p>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                className="mt-3 w-full"
                disabled={!selectedOps.length}
                loading={busyAction === "clean"}
                onClick={runClean}
              >
                <Wand2 className="h-3.5 w-3.5" /> Apply as new version
              </Button>
            </Card>
          </div>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-display text-[15px] font-semibold text-ink">Data preview</h2>
                <p className="mt-0.5 text-[12px] text-muted">First {preview.data?.preview_rows ?? 25} rows of the active version.</p>
              </div>
              <Badge tone="neutral"><FileText className="h-3 w-3" /> read-only</Badge>
            </div>
            <div className="mt-4">
              {preview.loading ? (
                <InlineLoader label="Loading rows" />
              ) : (
                <DataTable columns={previewColumns} data={preview.data?.rows ?? []} compact maxHeight={340} />
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="profile" className="space-y-4">
          {!prof ? (
            <InlineLoader label="Loading profile" />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {prof.columns.map((column) => (
                  <Card key={column.name} className="p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-[12.5px] font-medium text-ink">{column.name}</p>
                        <p className="mt-0.5 text-[10.5px] uppercase tracking-[0.1em] text-faint">{column.inferred_type}</p>
                      </div>
                      <Badge tone={column.null_pct > 20 ? "danger" : column.null_pct > 0 ? "warning" : "success"}>
                        {column.null_pct}% null
                      </Badge>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                      <span>{column.unique_count.toLocaleString()} unique</span>
                      <span>{column.unique_pct}%</span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-line/10">
                      <div className="h-full rounded-full bg-brand/70" style={{ width: `${Math.min(100, column.unique_pct)}%` }} />
                    </div>

                    {column.top_values.length > 0 && (
                      <div className="mt-3 space-y-1">
                        {column.top_values.slice(0, 3).map((item) => (
                          <div key={String(item.value)} className="flex items-center justify-between gap-2 text-[11px]">
                            <span className="truncate text-muted">{String(item.value)}</span>
                            <span className="font-mono text-faint">{item.count}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {Boolean(column.stats?.outliers?.count) && (
                      <p className="mt-2 flex items-center gap-1 text-[10.5px] text-warning">
                        <AlertTriangle className="h-3 w-3" /> {column.stats.outliers.count} IQR outliers flagged
                      </p>
                    )}
                    {column.issues.length > 0 && (
                      <p className="mt-1.5 line-clamp-2 text-[10.5px] text-faint">{column.issues[0]}</p>
                    )}
                  </Card>
                ))}
              </div>

              {prof.issues.length > 0 && (
                <Card className="p-5">
                  <h2 className="font-display text-[15px] font-semibold text-ink">Detected issues</h2>
                  <ul className="mt-3 space-y-2">
                    {prof.issues.map((issue, index) => (
                      <li key={`${issue.issue}-${index}`} className="flex items-start gap-2 text-[12.5px] text-muted">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                        <span><span className="font-medium text-ink">{issue.issue.replace(/_/g, " ")}</span> — {issue.detail}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="schema" className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-[15px] font-semibold text-ink">Physical schema</h2>
              {schema.data && <code className="rounded-md bg-line/[0.06] px-2 py-1 font-mono text-[11px] text-muted">{schema.data.table_name}</code>}
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {(schema.data?.columns ?? []).map((column) => (
                <div key={column.name} className="flex items-center justify-between gap-3 rounded-lg border border-line/10 px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <Columns3 className="h-3.5 w-3.5 shrink-0 text-faint" />
                    <span className="truncate font-mono text-[12px] text-ink">{column.name}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone="neutral">{column.type}</Badge>
                    {column.null_pct > 0 && <span className="text-[10.5px] text-faint">{column.null_pct}% null</span>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="space-y-4">
          <Card className="p-5">
            <h2 className="font-display text-[15px] font-semibold text-ink">Version history</h2>
            <p className="mt-0.5 text-[12px] text-muted">Original uploads are preserved; each cleaning operation produces a new immutable version.</p>
            <div className="mt-4 space-y-2">
              {(versions.data ?? []).map((version) => (
                <div key={version.id} className="flex flex-col gap-2 rounded-xl border border-line/10 bg-line/[0.02] p-3.5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/10 text-[11px] font-semibold text-brand">v{version.version_number}</span>
                    <div>
                      <p className="text-[12.5px] font-medium text-ink">
                        {version.row_count.toLocaleString()} rows · {version.column_count} columns
                        {version.version_number === data.active_version && <span className="ml-2 text-[10.5px] text-success">active</span>}
                      </p>
                      <p className="text-[11px] text-muted">
                        {version.applied_transformations.length
                          ? version.applied_transformations.map((t) => t.op.replace(/_/g, " ")).join(", ")
                          : "Original upload"}
                        {" · "}{formatDate(version.created_at, { month: "short", day: "numeric", year: "numeric" })}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {version.sheet_name && <Badge tone="neutral">sheet: {version.sheet_name}</Badge>}
                    <Badge tone="neutral">{version.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {data.dashboards && data.dashboards.length > 0 && (
        <Card className="p-5">
          <h2 className="font-display text-[15px] font-semibold text-ink">Dashboards from this dataset</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {data.dashboards.map((dashboard) => (
              <Link key={dashboard.id} href={`/app/dashboards/${dashboard.id}`} className="flex items-center justify-between rounded-xl border border-line/10 px-3.5 py-3 transition hover:border-brand/30">
                <div>
                  <p className="text-[13px] font-medium text-ink">{dashboard.title}</p>
                  <p className="text-[11px] text-muted">v{dashboard.version} · {dashboard.status}</p>
                </div>
                <ArrowUpRight className="h-4 w-4 text-faint" />
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
