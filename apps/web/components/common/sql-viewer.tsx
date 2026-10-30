"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export function SQLViewer({
  sql,
  label = "View SQL",
  meta,
  defaultOpen = false,
}: {
  sql: string;
  label?: string;
  meta?: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      toast.success("SQL copied to clipboard");
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Clipboard access was blocked by the browser");
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-line/10 bg-[#0B1024] text-[#D7DEF6]">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-[#9AA3C2] transition hover:text-white"
          aria-expanded={open}
        >
          <Database className="h-3.5 w-3.5" />
          {label}
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
        <div className="flex items-center gap-2">
          {meta}
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={copy}
            aria-label="Copy SQL"
            className="text-[#9AA3C2] hover:bg-white/10 hover:text-white"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>
      {open && (
        <pre className="max-h-64 overflow-auto p-3 text-[12px] leading-relaxed">
          <code className="whitespace-pre-wrap break-words font-mono">{sql || "-- no SQL was executed"}</code>
        </pre>
      )}
    </div>
  );
}
