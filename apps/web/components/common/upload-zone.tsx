"use client";

import { useCallback, useRef, useState } from "react";
import { FileSpreadsheet, FileText, UploadCloud, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/utils";

export function UploadZone({
  onSelect,
  disabled = false,
  maxMb = 50,
  value,
}: {
  onSelect: (file: File | null) => void;
  disabled?: boolean;
  maxMb?: number;
  value?: File | null;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const file = value ?? null;

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files?.length) return;
      onSelect(files[0]);
    },
    [onSelect],
  );

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) handleFiles(event.dataTransfer.files);
        }}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload a CSV or Excel file"
        className={cn(
          "relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-9 text-center transition",
          dragging ? "border-brand/60 bg-brand/[0.06]" : "border-line/20 hover:border-brand/40 hover:bg-line/[0.03]",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xlsm"
          className="sr-only"
          disabled={disabled}
          onChange={(event) => handleFiles(event.target.files)}
        />
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10 text-brand">
          <UploadCloud className="h-5 w-5" strokeWidth={1.7} />
        </span>
        {file ? (
          <div className="flex items-center gap-2 text-sm font-medium text-ink">
            {file.name.endsWith(".csv") ? <FileText className="h-4 w-4 text-cyan" /> : <FileSpreadsheet className="h-4 w-4 text-teal" />}
            {file.name}
            <button
              type="button"
              aria-label="Remove file"
              onClick={(event) => {
                event.stopPropagation();
                onSelect(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="rounded-full p-0.5 text-muted transition hover:bg-line/10 hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <>
            <div>
              <p className="text-sm font-medium text-ink">Drop a CSV or Excel workbook</p>
              <p className="mt-1 text-[12px] text-muted">or click to browse · max {maxMb} MB · .csv, .xlsx</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
