"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowDownRight, ArrowUpRight, Code2, Database, Loader2, MoreHorizontal, Minus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { EChart } from "@/components/charts/echart";
import { buildChartOption } from "@/lib/chart-options";
import { DataTable } from "@/components/common/data-table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SQLViewer } from "@/components/common/sql-viewer";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/components/ui/utils";
import { formatMetric } from "@/lib/format";
import { api, errorMessage } from "@/lib/api";
import type { Widget, WidgetData } from "@/lib/types";
import type { ColumnDef } from "@tanstack/react-table";

export function WidgetCard({
  dashboardId,
  widget,
  filters,
  refreshKey,
  editing,
  onRemove,
  onRetitle,
  onResize,
  onCrossFilter,
  datasetId,
}: {
  dashboardId: string;
  widget: Widget;
  filters: { field: string; operator: string; value: unknown }[];
  refreshKey: number;
  editing?: boolean;
  onRemove?: () => void;
  onRetitle?: (title: string) => void;
  onResize?: (width: number) => void;
  onCrossFilter?: (field: string, value: string) => void;
  datasetId: string;
}) {
  const [data, setData] = useState<WidgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localRefresh, setLocalRefresh] = useState(0);
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .post<WidgetData>(`/dashboards/${dashboardId}/widgets/${widget.id}/data`, { filters })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dashboardId, widget.id, JSON.stringify(filters), refreshKey, localRefresh]);

  const chartOption = useMemo(() => (data && data.rows.length ? buildChartOption(data, dark ? "dark" : "light") : {}), [data, dark]);

  const tableColumns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    if (!data) return [];
    return data.columns.map((column, index) => ({
      accessorFn: (row) => row[column],
      id: column,
      header: column.replace(/_/g, " "),
      cell: ({ getValue }) => {
        const value = getValue();
        if (value === null || value === undefined) return <span className="text-faint">—</span>;
        if (typeof value === "number") {
          return <span className="font-mono tabular-nums">{formatMetric(value, widget.options?.value_format ?? "number")}</span>;
        }
        if (index === 0 && /date|month|week|quarter|year/.test(column) && /^\d{4}-\d{2}/.test(String(value))) {
          return <span>{new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric" }).format(new Date(String(value)))}</span>;
        }
        return <span>{String(value)}</span>;
      },
    }));
  }, [data, widget.options?.value_format]);

  const tableRows = useMemo(() => {
    if (!data) return [];
    return data.rows.map((row) => Object.fromEntries(data.columns.map((column, index) => [column, row[index]])));
  }, [data]);

  const primaryValue = data?.rows?.[0]?.[0];
  const format = widget.options?.value_format ?? "number";
  const comparison = data?.comparison;
  const changePct =
    comparison && comparison.previous_value !== null && Number(comparison.previous_value) !== 0 && primaryValue !== null && primaryValue !== undefined
      ? ((Number(primaryValue) - Number(comparison.previous_value)) / Math.abs(Number(comparison.previous_value))) * 100
      : null;
  const height = widget.type === "kpi" ? 0 : widget.type === "data_table" ? 336 : 300;

  const handleChartClick = (params: { name?: string; seriesName?: string }) => {
    if (!onCrossFilter || !data) return;
    const encoding = data.encoding as Record<string, string | string[]>;
    const field = typeof encoding.x === "string" ? encoding.x : typeof encoding.label === "string" ? encoding.label : null;
    if (!field || !params.name) return;
    onCrossFilter(field, params.name);
  };

  return (
    <div className="glass group relative flex flex-col overflow-hidden rounded-2xl">
      <div className="flex items-start justify-between gap-2 px-4 pb-2 pt-3.5">
        <div className="min-w-0">
          {editing ? (
            <input
              value={widget.title}
              onChange={(event) => onRetitle?.(event.target.value)}
              aria-label="Widget title"
              className="w-full rounded-md border border-transparent bg-transparent px-1 py-0.5 font-display text-[13.5px] font-semibold text-ink outline-none focus:border-line/20"
            />
          ) : (
            <h3 className="truncate font-display text-[13.5px] font-semibold text-ink">{widget.title}</h3>
          )}
          {widget.description && !editing && (
            <p className="mt-0.5 line-clamp-1 text-[11px] text-muted">{widget.description}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-faint" />}
          {editing ? (
            <div className="flex items-center gap-1">
              <select
                aria-label="Widget width"
                value={widget.layout.w}
                onChange={(event) => onResize?.(Number(event.target.value))}
                className="rounded-md border border-line/15 bg-surface px-1.5 py-1 text-[10.5px] text-muted"
              >
                <option value={3}>1/4</option>
                <option value={4}>1/3</option>
                <option value={6}>1/2</option>
                <option value={8}>2/3</option>
                <option value={12}>Full</option>
              </select>
              <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label="Remove widget">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="Widget actions" className="opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-[210px]">
                <Dialog>
                  <DialogTrigger asChild>
                    <DropdownMenuItem onSelect={(event) => event.preventDefault()}>
                      <Code2 className="h-3.5 w-3.5" /> View SQL
                    </DropdownMenuItem>
                  </DialogTrigger>
                  <DialogContent className="max-w-2xl">
                    <DialogHeader>
                      <DialogTitle>{widget.title}</DialogTitle>
                    </DialogHeader>
                    <div className="mt-4 space-y-3">
                      <SQLViewer sql={data?.sql ?? "-- query not executed"} defaultOpen />
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                        <Badge tone="neutral"><Database className="h-3 w-3" /> {data?.row_count ?? 0} rows</Badge>
                        <span>{data?.duration_ms ? `${data.duration_ms.toFixed(1)} ms` : ""}</span>
                        <span className="font-mono">{JSON.stringify(data?.query_spec ?? {})}</span>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
                <DropdownMenuItem asChild>
                  <Link href={`/app/analyst?datasetId=${datasetId}&q=${encodeURIComponent(`Explain the widget "${widget.title}"`)}`}>
                    <ArrowUpRight className="h-3.5 w-3.5" /> Ask the analyst
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setLocalRefresh((v) => v + 1)}>
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh widget
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <div className="flex-1 px-4 pb-4">
        {error ? (
          <div className="flex h-[180px] flex-col items-center justify-center gap-2 rounded-xl border border-danger/20 bg-danger/[0.05] p-4 text-center">
            <AlertCircle className="h-4 w-4 text-danger" />
            <p className="text-[12px] text-danger">{error}</p>
            <Button variant="outline" size="sm" onClick={() => setLocalRefresh((v) => v + 1)}>Retry</Button>
          </div>
        ) : loading && !data ? (
          <div className="skeleton" style={{ height: height || 80 }} />
        ) : widget.type === "kpi" ? (
          <div className="pt-1">
            <p className="kpi-value text-[28px] font-semibold leading-none text-ink">
              {primaryValue === undefined || primaryValue === null ? "—" : formatMetric(Number(primaryValue), format)}
            </p>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              {changePct !== null ? (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10.5px] font-medium tabular-nums",
                    changePct > 0.05
                      ? "border-success/25 bg-success/10 text-success"
                      : changePct < -0.05
                        ? "border-danger/25 bg-danger/10 text-danger"
                        : "border-line/15 bg-line/[0.05] text-muted",
                  )}
                  title={`Previous period ${comparison?.previous_start} → ${comparison?.previous_end}`}
                >
                  {changePct > 0.05 ? <ArrowUpRight className="h-3 w-3" /> : changePct < -0.05 ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                  {changePct > 0 ? "+" : ""}{changePct.toFixed(1)}%
                  <span className="font-normal text-muted">vs prev {comparison?.period_days}d</span>
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  computed from {data?.row_count ?? 0} row{data?.row_count === 1 ? "" : "s"}
                </span>
              )}
            </div>
          </div>
        ) : widget.type === "data_table" ? (
          <DataTable columns={tableColumns} data={tableRows} compact maxHeight={300} emptyMessage="No rows returned for these filters." />
        ) : data && data.rows.length ? (
          <EChart
            option={chartOption}
            height={height}
            onSelect={handleChartClick}
            ariaLabel={`${widget.title} chart`}
            className={cn(onCrossFilter && "cursor-pointer")}
          />
        ) : (
          <div className="flex h-[180px] flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-line/15 text-center">
            <p className="text-[12px] text-muted">No data for the current filters</p>
            <p className="text-[11px] text-faint">Adjust filters or refresh the widget.</p>
          </div>
        )}
      </div>
    </div>
  );
}
