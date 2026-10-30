"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, BarChart3, Bot, Check, Clock, Filter, History, Pencil, Plus, RefreshCw,
  Rocket, Sparkles, X,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PageSkeleton } from "@/components/common/loading";
import { EmptyState } from "@/components/common/empty-state";
import { WidgetCard } from "@/components/dashboard/widget-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DashboardDetail, Dataset, SemanticDefinition, Widget } from "@/lib/types";

type RuntimeFilter = { field: string; operator: string; value: unknown };

interface FilterState {
  [field: string]: { value?: string; start?: string; end?: string };
}

const WIDGET_TYPES = [
  { value: "kpi", label: "KPI card" },
  { value: "bar_chart", label: "Bar chart" },
  { value: "line_chart", label: "Line chart" },
  { value: "area_chart", label: "Area chart" },
  { value: "donut_chart", label: "Donut chart" },
  { value: "data_table", label: "Data table" },
];

export default function DashboardPage() {
  const params = useParams<{ id: string }>();
  const dashboardId = params.id;
  const router = useRouter();
  const { data, loading, error, refresh } = useApi<DashboardDetail>(`/dashboards/${dashboardId}`);
  const dataset = useApi<Dataset>(data ? `/datasets/${data.dataset_id}` : null);

  const [spec, setSpec] = useState<DashboardDetail["specification"] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [filters, setFilters] = useState<FilterState>({});
  const [crossFilter, setCrossFilter] = useState<{ field: string; value: string } | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newWidget, setNewWidget] = useState({ type: "bar_chart", title: "New widget", metric: "", dimension: "" });

  useEffect(() => {
    if (!data?.specification) return;
    setSpec(structuredClone(data.specification));
    setDirty(false);
    // Seed filters from the specification's declared defaults so KPI
    // comparisons always run against an explicit, equal-length window.
    const initial: FilterState = {};
    for (const definition of data.specification.filters) {
      const defaultValue = definition.default_value as { start?: string; end?: string } | undefined;
      if (definition.type === "date_range" && defaultValue?.start && defaultValue?.end) {
        initial[definition.field] = { start: defaultValue.start, end: defaultValue.end };
      }
    }
    setFilters(initial);
  }, [data]);

  const semantic: SemanticDefinition | undefined = data?.semantic;
  const filtersSpec = spec?.filters ?? [];
  const allowedFilterFields = useMemo(() => new Set(filtersSpec.map((item) => item.field)), [filtersSpec]);

  const runtimeFilters = useMemo<RuntimeFilter[]>(() => {
    const result: RuntimeFilter[] = [];
    for (const definition of filtersSpec) {
      const state = filters[definition.field];
      if (!state) continue;
      if (definition.type === "categorical" && state.value) {
        result.push({ field: definition.field, operator: "eq", value: state.value });
      }
      if (definition.type === "date_range") {
        if (state.start) result.push({ field: definition.field, operator: "gte", value: state.start });
        if (state.end) result.push({ field: definition.field, operator: "lte", value: state.end });
      }
    }
    if (crossFilter) result.push({ field: crossFilter.field, operator: "eq", value: crossFilter.value });
    return result;
  }, [filters, filtersSpec, crossFilter]);

  const widgets = useMemo(
    () => [...(spec?.widgets ?? [])].sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x),
    [spec],
  );

  const save = async (): Promise<boolean> => {
    if (!spec) return false;
    setSaving(true);
    try {
      await api.put(`/dashboards/${dashboardId}`, { specification: spec });
      toast.success("Dashboard saved", { description: "A new immutable version was created." });
      setDirty(false);
      refresh();
      return true;
    } catch (err) {
      toast.error(errorMessage(err));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    setPublishing(true);
    try {
      if (dirty && !(await save())) return;
      await api.post(`/dashboards/${dashboardId}/publish`);
      toast.success("Dashboard published", { description: "The latest version is now live." });
      refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPublishing(false);
    }
  };

  const updateWidget = (index: number, changes: Partial<Widget>) => {
    setSpec((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      const targetId = widgets[index].id;
      const realIndex = draft.widgets.findIndex((widget) => widget.id === targetId);
      draft.widgets[realIndex] = { ...draft.widgets[realIndex], ...changes };
      return draft;
    });
    setDirty(true);
  };

  const removeWidget = (id: string) => {
    setSpec((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      draft.widgets = draft.widgets.filter((widget) => widget.id !== id);
      return draft;
    });
    setDirty(true);
  };

  const addWidget = () => {
    if (!spec) return;
    const metric = newWidget.metric;
    const dimension = newWidget.dimension;
    if (!metric) {
      toast.error("Select a metric for the new widget");
      return;
    }
    if (newWidget.type !== "kpi" && !dimension) {
      toast.error("This chart type needs a dimension");
      return;
    }
    const slug = `custom_${Date.now().toString(36)}`;
    const queryRef = `query_${slug}`;
    const draft = structuredClone(spec);
    draft.queries[queryRef] = {
      metrics: [metric],
      group_by: dimension ? [dimension] : [],
      grain: null,
      filters: [],
      order_by: dimension ? { field: metric, direction: "desc" } : null,
      limit: dimension ? 10 : 1,
    };
    const encoding: Record<string, string | string[]> =
      newWidget.type === "kpi"
        ? { value: metric }
        : newWidget.type === "donut_chart"
          ? { label: dimension, value: metric }
          : newWidget.type === "data_table"
            ? { columns: dimension ? [dimension, metric] : [metric] }
            : { x: dimension, y: [metric] };
    const maxY = Math.max(0, ...draft.widgets.map((widget) => widget.layout.y + widget.layout.h));
    draft.widgets.push({
      id: slug,
      type: newWidget.type as Widget["type"],
      title: newWidget.title || "New widget",
      description: "",
      query_ref: queryRef,
      encoding,
      layout: { x: 0, y: maxY, w: newWidget.type === "kpi" ? 3 : 6, h: newWidget.type === "kpi" ? 2 : 4 },
      interactions: { cross_filter: false, click_to_ask: true },
      options: { value_format: semantic?.metrics.find((entry) => entry.name === metric)?.format ?? "number", sort: "desc" },
    });
    setSpec(draft);
    setDirty(true);
    setAddOpen(false);
    setNewWidget({ type: "bar_chart", title: "New widget", metric: "", dimension: "" });
  };

  const regenerate = async () => {
    if (!spec) return;
    try {
      await api.post("/dashboards/generate", { dataset_id: spec.dataset_id, mode: "review" });
      toast.success("Dashboard regenerated", { description: "A new review version is ready." });
      refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  if (loading) return <PageSkeleton />;
  if (error || !data || !spec) {
    return (
      <div className="glass rounded-2xl">
        <EmptyState
          icon={BarChart3}
          title="Dashboard not available"
          description={error || "This dashboard may have been removed."}
          action={<Button asChild variant="outline"><Link href="/app/dashboards"><ArrowLeft className="h-4 w-4" /> Back to dashboards</Link></Button>}
        />
      </div>
    );
  }

  const datasetName = dataset.data?.name ?? "Dataset";

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <Link href="/app/dashboards" className="inline-flex items-center gap-1 transition hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> Dashboards
        </Link>
        <span className="text-faint">/</span>
        <span className="text-ink">{spec.title}</span>
      </div>

      <PageHeader
        eyebrow={`${datasetName} · semantic v${spec.semantic_model_version} · version ${data.version}`}
        title={spec.title}
        description={spec.description}
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setRefreshKey((key) => key + 1)}>
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link href={`/app/analyst?datasetId=${spec.dataset_id}`}><Bot className="h-3.5 w-3.5" /> Ask analyst</Link>
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="ghost" size="sm"><History className="h-3.5 w-3.5" /> Versions</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Version history</DialogTitle>
                  <DialogDescription>Every save is immutable; publishing points the dashboard at a version.</DialogDescription>
                </DialogHeader>
                <div className="mt-4">
                  <VersionList dashboardId={dashboardId} />
                </div>
              </DialogContent>
            </Dialog>
            {editing ? (
              <>
                <Button variant="outline" size="sm" onClick={() => { setSpec(structuredClone(data.specification)); setEditing(false); setDirty(false); }}>
                  <X className="h-3.5 w-3.5" /> Cancel
                </Button>
                <Button variant="gradient" size="sm" onClick={save} loading={saving}>
                  <Check className="h-3.5 w-3.5" /> Save version
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </Button>
                {data.status !== "published" ? (
                  <Button variant="gradient" size="sm" onClick={publish} loading={publishing}>
                    <Rocket className="h-3.5 w-3.5" /> Publish
                  </Button>
                ) : (
                  <Badge tone="success" className="h-8 px-3"><Check className="h-3.5 w-3.5" /> Published</Badge>
                )}
              </>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={data.status === "published" ? "success" : "warning"}>{data.status}</Badge>
        <Badge tone="neutral"><Clock className="h-3 w-3" /> {formatDate(data.updated_at, { month: "short", day: "numeric" })}</Badge>
        {dirty && <Badge tone="brand">Unsaved changes</Badge>}
        <span className="text-[11.5px] text-faint">{spec.widgets.length} widgets · {spec.queries ? Object.keys(spec.queries).length : 0} validated queries</span>
        {dataset.data?.is_synthetic && <Badge tone="violet">Synthetic demo data</Badge>}
      </div>

      {/* Filters */}
      <div className="glass flex flex-wrap items-end gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-2 pb-2 pr-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
          <Filter className="h-3.5 w-3.5" /> Filters
        </div>
        {filtersSpec.length === 0 && <p className="pb-2 text-[12px] text-muted">No filters were defined for this dashboard.</p>}
        {filtersSpec.map((definition) => (
          <div key={definition.id} className="min-w-[160px]">
            <Label className="text-[10.5px] uppercase tracking-[0.1em] text-faint">{definition.label}</Label>
            {definition.type === "categorical" ? (
              <FilterSelect
                datasetId={spec.dataset_id}
                field={definition.field}
                value={filters[definition.field]?.value ?? ""}
                onChange={(value) =>
                  setFilters((current) => ({
                    ...current,
                    [definition.field]: { ...current[definition.field], value: value === "__all__" ? undefined : value },
                  }))
                }
              />
            ) : (
              <div className="mt-1 flex items-center gap-1.5">
                <input
                  type="date"
                  aria-label={`${definition.label} start`}
                  value={filters[definition.field]?.start ?? ""}
                  onChange={(event) => setFilters((current) => ({ ...current, [definition.field]: { ...current[definition.field], start: event.target.value } }))}
                  className="h-9 rounded-lg border border-line/12 bg-surface/70 px-2 text-[12px] text-ink"
                />
                <span className="text-faint">–</span>
                <input
                  type="date"
                  aria-label={`${definition.label} end`}
                  value={filters[definition.field]?.end ?? ""}
                  onChange={(event) => setFilters((current) => ({ ...current, [definition.field]: { ...current[definition.field], end: event.target.value } }))}
                  className="h-9 rounded-lg border border-line/12 bg-surface/70 px-2 text-[12px] text-ink"
                />
              </div>
            )}
          </div>
        ))}
        {(Object.keys(filters).length > 0 || crossFilter) && (
          <Button variant="ghost" size="sm" className="mb-0.5" onClick={() => { setFilters({}); setCrossFilter(null); }}>
            <X className="h-3.5 w-3.5" /> Clear
          </Button>
        )}
        {crossFilter && (
          <Badge tone="brand" className="mb-1.5">
            {crossFilter.field}: {crossFilter.value}
            <button type="button" onClick={() => setCrossFilter(null)} aria-label="Clear cross-filter"><X className="h-3 w-3" /></button>
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2 pb-0.5">
          {editing && (
            <Dialog>
              <DialogTrigger asChild>
                <Button size="sm" variant="outline"><Plus className="h-3.5 w-3.5" /> Add widget</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Add a widget</DialogTitle>
                  <DialogDescription>Choose from the trusted widget registry. Queries are built and validated by the backend.</DialogDescription>
                </DialogHeader>
                <div className="mt-4 space-y-3">
                  <div className="space-y-1.5">
                    <Label>Widget type</Label>
                    <Select value={newWidget.type} onValueChange={(value) => setNewWidget((current) => ({ ...current, type: value }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {WIDGET_TYPES.map((type) => <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Title</Label>
                    <Input value={newWidget.title} onChange={(event) => setNewWidget((current) => ({ ...current, title: event.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Metric</Label>
                    <Select value={newWidget.metric} onValueChange={(value) => setNewWidget((current) => ({ ...current, metric: value }))}>
                      <SelectTrigger><SelectValue placeholder="Choose metric" /></SelectTrigger>
                      <SelectContent>
                        {(semantic?.metrics ?? []).map((metric) => <SelectItem key={metric.name} value={metric.name}>{metric.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  {newWidget.type !== "kpi" && (
                    <div className="space-y-1.5">
                      <Label>Dimension</Label>
                      <Select value={newWidget.dimension} onValueChange={(value) => setNewWidget((current) => ({ ...current, dimension: value }))}>
                        <SelectTrigger><SelectValue placeholder="Choose dimension" /></SelectTrigger>
                        <SelectContent>
                          {(semantic?.dimensions ?? []).filter((dimension) => dimension.data_type !== "identifier").map((dimension) => (
                            <SelectItem key={dimension.name} value={dimension.name}>{dimension.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <Button className="w-full" variant="gradient" onClick={addWidget}>Add widget</Button>
                </div>
              </DialogContent>
            </Dialog>
          )}
          <Button size="sm" variant="ghost" onClick={regenerate}>
            <Sparkles className="h-3.5 w-3.5" /> Regenerate
          </Button>
        </div>
      </div>

      <div className="widget-grid">
        {widgets.map((widget, index) => (
          <div key={widget.id} className="widget-cell" style={{ ["--widget-w" as string]: String(widget.layout.w) }}>
            <WidgetCard
              dashboardId={dashboardId}
              widget={widget}
              filters={runtimeFilters}
              refreshKey={refreshKey}
              editing={editing}
              datasetId={spec.dataset_id}
              onRemove={() => removeWidget(widget.id)}
              onRetitle={(title) => updateWidget(index, { title })}
              onResize={(width) => updateWidget(index, { layout: { ...widget.layout, w: width } })}
              onCrossFilter={(field, value) => {
                if (!allowedFilterFields.has(field)) {
                  toast.info("Cross-filter unavailable", { description: `Add a filter on "${field}" to enable click-to-filter.` });
                  return;
                }
                setCrossFilter((current) => (current?.field === field && current.value === value ? null : { field, value }));
              }}
            />
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between rounded-2xl border border-line/10 bg-line/[0.02] px-4 py-3 text-[11.5px] text-muted">
        <span>Rendered from a validated dashboard specification — no generated code executes in the browser.</span>
        <Link href={`/app/analyst?datasetId=${spec.dataset_id}`} className="flex items-center gap-1 font-medium text-brand hover:underline">
          Investigate with the analyst <Bot className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

function FilterSelect({
  datasetId,
  field,
  value,
  onChange,
}: {
  datasetId: string;
  field: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { data } = useApi<{ values: (string | number)[] }>(`/datasets/${datasetId}/values?field=${encodeURIComponent(field)}`);
  return (
    <Select value={value || "__all__"} onValueChange={onChange}>
      <SelectTrigger className="mt-1 h-9"><SelectValue placeholder="All" /></SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">All</SelectItem>
        {(data?.values ?? []).map((option) => (
          <SelectItem key={String(option)} value={String(option)}>{String(option)}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function VersionList({ dashboardId }: { dashboardId: string }) {
  const { data, loading } = useApi<
    { id: string; version_number: number; generated_by: string; created_at: string; widget_count: number; is_active: boolean; validation: { valid?: boolean } }[]
  >(`/dashboards/${dashboardId}/versions`);
  if (loading) return <div className="h-24 skeleton rounded-xl" />;
  return (
    <div className="max-h-[320px] space-y-2 overflow-y-auto">
      {(data ?? []).map((version) => (
        <div key={version.id} className="flex items-center justify-between rounded-xl border border-line/10 px-3 py-2.5">
          <div>
            <p className="text-[12.5px] font-medium text-ink">v{version.version_number} · {version.generated_by.replace(/_/g, " ")}</p>
            <p className="text-[11px] text-muted">{version.widget_count} widgets · {formatDate(version.created_at, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</p>
          </div>
          {version.is_active ? <Badge tone="success">active</Badge> : <Badge tone="neutral">archived</Badge>}
        </div>
      ))}
    </div>
  );
}
