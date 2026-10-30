"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Check, Layers, Plus, RefreshCw, Save, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PageSkeleton, InlineLoader } from "@/components/common/loading";
import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import type { Dataset, DimensionDefinition, MetricDefinition, SemanticDefinition, SemanticModel } from "@/lib/types";

const AGGREGATIONS = ["SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX", "MEDIAN", "RATIO"];
const FORMATS = ["currency", "integer", "decimal", "percent", "number"];
const GRAINS = ["day", "week", "month", "quarter", "year"];

export default function SemanticEditorPage() {
  const params = useParams<{ id: string }>();
  const datasetId = params.id;
  const router = useRouter();
  const dataset = useApi<Dataset>(`/datasets/${datasetId}`);
  const model = useApi<SemanticModel>(`/semantic-models/dataset/${datasetId}`);
  const [definition, setDefinition] = useState<SemanticDefinition | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (model.data) {
      setDefinition(structuredClone(model.data.definition));
      setDirty(false);
    }
  }, [model.data]);

  const columns = dataset.data?.active_version_detail?.profile?.columns ?? [];
  const availableColumns = useMemo(() => columns.map((column) => column.name), [columns]);
  const approved = model.data?.status === "approved";

  const update = (mutator: (draft: SemanticDefinition) => void) => {
    setDefinition((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      mutator(draft);
      setDirty(true);
      return draft;
    });
  };

  const save = async () => {
    if (!definition || !model.data) return;
    setBusy("save");
    try {
      const result = await api.put<SemanticModel & { validation?: { warnings: string[]; dropped_metrics: string[] } }>(
        `/semantic-models/${model.data.id}`,
        { definition },
      );
      toast.success("Semantic model saved", {
        description: result.validation?.warnings?.length ? `${result.validation.warnings.length} validation warning(s)` : "Draft updated",
      });
      setDirty(false);
      model.refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const approve = async () => {
    if (!model.data) return;
    setBusy("approve");
    try {
      if (dirty) await save();
      const result = await api.post<SemanticModel & { dashboard_draft?: { id: string } }>(
        `/semantic-models/${model.data.id}/approve`,
        { approved: true, version: model.data.version },
      );
      toast.success("Semantic model approved", { description: "A dashboard draft was generated for review." });
      model.refresh();
      if (result.dashboard_draft?.id) router.push(`/app/dashboards/${result.dashboard_draft.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const regenerate = async () => {
    setBusy("regenerate");
    try {
      await api.post("/semantic-models/generate", { dataset_id: datasetId, regenerate: true });
      toast.success("New semantic proposal generated");
      model.refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  if (dataset.loading || model.loading) return <PageSkeleton />;
  if (model.error || !model.data || !definition) {
    return (
      <div className="glass rounded-2xl">
        <EmptyState
          icon={Layers}
          title="No semantic model yet"
          description={model.error || "Generate a semantic model from the dataset profile first."}
          action={
            <div className="flex gap-2">
              <Button asChild variant="outline"><Link href={`/app/datasets/${datasetId}`}><ArrowLeft className="h-4 w-4" /> Back to dataset</Link></Button>
              <Button variant="gradient" loading={busy === "regenerate"} onClick={regenerate}><Sparkles className="h-4 w-4" /> Generate proposal</Button>
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <Link href={`/app/datasets/${datasetId}`} className="inline-flex items-center gap-1 transition hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> {dataset.data?.name ?? "Dataset"}
        </Link>
        <span className="text-faint">/</span>
        <span className="text-ink">Semantic model</span>
      </div>

      <PageHeader
        eyebrow={`Version ${model.data.version} · proposed by ${model.data.generated_by}`}
        title="Semantic model review"
        description="Every metric and dimension is validated against the physical schema. Approving publishes the definitions to dashboards, the analyst and retrieval."
        actions={
          <>
            <Button variant="outline" onClick={regenerate} loading={busy === "regenerate"}>
              <RefreshCw className="h-4 w-4" /> Regenerate
            </Button>
            <Button variant="outline" onClick={save} loading={busy === "save"} disabled={!dirty}>
              <Save className="h-4 w-4" /> Save draft
            </Button>
            <Button variant="gradient" onClick={approve} loading={busy === "approve"} disabled={approved}>
              <ShieldCheck className="h-4 w-4" /> {approved ? "Approved" : "Approve model"}
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={approved ? "success" : model.data.status === "rejected" ? "danger" : "warning"}>
          {model.data.status}
        </Badge>
        {dirty && <Badge tone="brand">Unsaved changes</Badge>}
        <span className="text-[11.5px] text-faint">Grain: {definition.grain}</span>
        {approved && <span className="text-[11.5px] text-faint">Approved {model.data.approved_at ? new Date(model.data.approved_at).toLocaleDateString() : ""}</span>}
      </div>

      <Tabs defaultValue="metrics">
        <TabsList>
          <TabsTrigger value="metrics">Metrics ({definition.metrics.length})</TabsTrigger>
          <TabsTrigger value="dimensions">Dimensions ({definition.dimensions.length})</TabsTrigger>
          <TabsTrigger value="time">Time & relationships</TabsTrigger>
          <TabsTrigger value="glossary">Business definitions</TabsTrigger>
        </TabsList>

        <TabsContent value="metrics" className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-[12px] text-muted">Aggregations are executed exactly as defined — approval clears the &quot;needs approval&quot; flag.</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                update((draft) => {
                  draft.metrics.push({
                    name: `new_metric_${draft.metrics.length + 1}`,
                    label: "New metric",
                    source_column: availableColumns[0] ?? "",
                    aggregation: "SUM",
                    format: "number",
                    description: "",
                    requires_approval: true,
                    confidence: 0.5,
                  });
                })
              }
            >
              <Plus className="h-3.5 w-3.5" /> Add metric
            </Button>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {definition.metrics.map((metric, index) => (
              <Card key={`${metric.name}-${index}`} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Input
                      aria-label="Metric label"
                      value={metric.label}
                      onChange={(event) => update((draft) => { draft.metrics[index].label = event.target.value; })}
                      className="h-8 border-transparent bg-transparent px-1 font-display text-[14px] font-semibold focus-visible:border-line/20"
                    />
                    <p className="mt-1 font-mono text-[11px] text-faint">{metric.name}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    {metric.requires_approval ? <Badge tone="warning">review</Badge> : <Badge tone="success">confirmed</Badge>}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove ${metric.label}`}
                      onClick={() => update((draft) => { draft.metrics.splice(index, 1); })}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-[11px] text-faint">Aggregation</Label>
                    <Select
                      value={metric.aggregation}
                      onValueChange={(value) => update((draft) => { draft.metrics[index].aggregation = value; })}
                    >
                      <SelectTrigger className="mt-1 h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {AGGREGATIONS.map((aggregation) => <SelectItem key={aggregation} value={aggregation}>{aggregation.replace("_", " ")}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-[11px] text-faint">Format</Label>
                    <Select
                      value={metric.format}
                      onValueChange={(value) => update((draft) => { draft.metrics[index].format = value; })}
                    >
                      <SelectTrigger className="mt-1 h-8"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {FORMATS.map((format) => <SelectItem key={format} value={format}>{format}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="mt-2">
                  <Label className="text-[11px] text-faint">Source column</Label>
                  <Select
                    value={metric.source_column}
                    onValueChange={(value) => update((draft) => { draft.metrics[index].source_column = value; })}
                  >
                    <SelectTrigger className="mt-1 h-8"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {availableColumns.map((column) => <SelectItem key={column} value={column}>{column}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>

                {metric.aggregation === "RATIO" && (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-[11px] text-faint">Numerator metric</Label>
                      <Select value={metric.numerator ?? ""} onValueChange={(value) => update((draft) => { draft.metrics[index].numerator = value; })}>
                        <SelectTrigger className="mt-1 h-8"><SelectValue placeholder="metric" /></SelectTrigger>
                        <SelectContent>
                          {definition.metrics.filter((entry) => entry.name !== metric.name).map((entry) => (
                            <SelectItem key={entry.name} value={entry.name}>{entry.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-[11px] text-faint">Denominator metric</Label>
                      <Select value={metric.denominator ?? ""} onValueChange={(value) => update((draft) => { draft.metrics[index].denominator = value; })}>
                        <SelectTrigger className="mt-1 h-8"><SelectValue placeholder="metric" /></SelectTrigger>
                        <SelectContent>
                          {definition.metrics.filter((entry) => entry.name !== metric.name).map((entry) => (
                            <SelectItem key={entry.name} value={entry.name}>{entry.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}

                <Textarea
                  aria-label="Metric description"
                  className="mt-2 min-h-[62px] text-[12px]"
                  value={metric.description ?? ""}
                  onChange={(event) => update((draft) => { draft.metrics[index].description = event.target.value; })}
                  placeholder="Business meaning, caveats and assumptions…"
                />
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="dimensions" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[12px] text-muted">Identifier columns are available for counting but excluded from default grouping.</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                update((draft) => {
                  draft.dimensions.push({
                    name: `new_dimension_${draft.dimensions.length + 1}`,
                    label: "New dimension",
                    source_column: availableColumns[0] ?? "",
                    data_type: "categorical",
                    description: "",
                    confirmed: false,
                  });
                })
              }
            >
              <Plus className="h-3.5 w-3.5" /> Add dimension
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {definition.dimensions.map((dimension, index) => (
              <Card key={`${dimension.name}-${index}`} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <Input
                    aria-label="Dimension label"
                    value={dimension.label}
                    onChange={(event) => update((draft) => { draft.dimensions[index].label = event.target.value; })}
                    className="h-8 border-transparent bg-transparent px-1 text-[13.5px] font-semibold focus-visible:border-line/20"
                  />
                  <Button variant="ghost" size="icon-sm" aria-label="Remove dimension" onClick={() => update((draft) => { draft.dimensions.splice(index, 1); })}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <p className="font-mono text-[11px] text-faint">{dimension.source_column}</p>
                <div className="mt-2 flex items-center gap-2">
                  <Badge tone={dimension.data_type === "identifier" ? "neutral" : "brand"}>{dimension.data_type}</Badge>
                  <span className="text-[11px] text-muted">{dimension.confirmed ? "confirmed" : "inferred"}</span>
                </div>
                <Textarea
                  className="mt-2 min-h-[56px] text-[11.5px]"
                  aria-label="Dimension description"
                  value={dimension.description ?? ""}
                  onChange={(event) => update((draft) => { draft.dimensions[index].description = event.target.value; })}
                />
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="time" className="space-y-4">
          <Card className="p-5">
            <h2 className="font-display text-[15px] font-semibold text-ink">Time dimensions</h2>
            <p className="mt-0.5 text-[12px] text-muted">Used for trends, period comparisons and the dashboard date filter.</p>
            <div className="mt-4 space-y-2">
              {definition.time_dimensions.length === 0 && <p className="text-[12px] text-faint">No date columns were inferred for this dataset.</p>}
              {definition.time_dimensions.map((time, index) => (
                <div key={`${time.name}-${index}`} className="flex flex-col gap-3 rounded-xl border border-line/10 p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-[13px] font-medium text-ink">{time.label}</p>
                    <p className="font-mono text-[11px] text-faint">{time.source_column}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label className="text-[11px] text-faint">Default grain</Label>
                    <Select value={time.default_grain ?? "month"} onValueChange={(value) => update((draft) => { draft.time_dimensions[index].default_grain = value; })}>
                      <SelectTrigger className="h-8 w-[120px]"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {GRAINS.map((grain) => <SelectItem key={grain} value={grain}>{grain}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="font-display text-[15px] font-semibold text-ink">Relationships</h2>
            <p className="mt-0.5 text-[12px] text-muted">
              Single-dataset analytics is the MVP scope. Relationships remain declarative so multi-table models can be
              added without changing the dashboard or agent contracts.
            </p>
            <div className="mt-3">
              {definition.relationships.length === 0 ? (
                <p className="rounded-xl border border-line/10 bg-line/[0.02] p-3 text-[12px] text-muted">
                  No cross-column relationships were inferred. Identifier columns are listed under dimensions.
                </p>
              ) : (
                definition.relationships.map((relationship, index) => (
                  <div key={index} className="mt-2 flex items-center justify-between rounded-lg border border-line/10 px-3 py-2 text-[12px]">
                    <span className="font-mono text-ink">{relationship.from_column} → {relationship.to_column}</span>
                    <Badge tone="neutral">{relationship.type}</Badge>
                  </div>
                ))
              )}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="glossary" className="space-y-3">
          <p className="text-[12px] text-muted">
            These definitions are embedded into tenant-scoped retrieval, so the analyst can explain terminology — not
            calculate with it.
          </p>
          {definition.business_definitions.map((entry, index) => (
            <Card key={`${entry.term}-${index}`} className="p-4">
              <Input
                value={entry.term}
                aria-label="Glossary term"
                className="h-8 border-transparent bg-transparent px-1 font-display text-[13.5px] font-semibold focus-visible:border-line/20"
                onChange={(event) => update((draft) => { draft.business_definitions[index].term = event.target.value; })}
              />
              <Textarea
                className="mt-1 min-h-[60px] text-[12px]"
                aria-label="Glossary definition"
                value={entry.definition}
                onChange={(event) => update((draft) => { draft.business_definitions[index].definition = event.target.value; })}
              />
            </Card>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => update((draft) => { draft.business_definitions.push({ term: "New term", definition: "" }); })}
          >
            <Plus className="h-3.5 w-3.5" /> Add definition
          </Button>
        </TabsContent>
      </Tabs>

      {!approved && (
        <div className="flex flex-col items-start justify-between gap-3 rounded-2xl border border-brand/20 bg-brand/[0.06] p-4 sm:flex-row sm:items-center">
          <div className="flex items-start gap-2.5">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
            <p className="text-[12.5px] leading-relaxed text-muted">
              Approving locks version {model.data.version} as the business definition and generates a dashboard draft
              for review. You can create a new version later without losing this one.
            </p>
          </div>
          <Button variant="gradient" onClick={approve} loading={busy === "approve"} className="shrink-0">
            <Check className="h-4 w-4" /> Approve & generate draft
          </Button>
        </div>
      )}
    </div>
  );
}
