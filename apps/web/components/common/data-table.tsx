"use client";

import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";
import { cn } from "@/components/ui/utils";

export function DataTable<T>({
  columns,
  data,
  emptyMessage = "No rows to display.",
  compact = false,
  maxHeight,
}: {
  columns: ColumnDef<T, any>[];
  data: T[];
  emptyMessage?: string;
  compact?: boolean;
  maxHeight?: number;
}) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="overflow-hidden rounded-xl border border-line/10" style={maxHeight ? { maxHeight, overflowY: "auto" } : undefined}>
      <table className="w-full border-collapse text-left text-[13px]">
        <thead className="sticky top-0 z-10 bg-line/[0.04] backdrop-blur">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className={cn(
                    "whitespace-nowrap border-b border-line/10 font-medium text-faint",
                    compact ? "px-3 py-2 text-[11px] uppercase tracking-wider" : "px-4 py-2.5 text-[11px] uppercase tracking-wider",
                  )}
                >
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-10 text-center text-muted">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="table-row-hover border-b border-line/[0.06] last:border-0">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className={cn("align-top text-ink/90", compact ? "px-3 py-1.5" : "px-4 py-2.5")}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export const SortIcon = ArrowUpDown;
