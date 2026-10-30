"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileSpreadsheet, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UploadZone } from "@/components/common/upload-zone";
import { api, errorMessage } from "@/lib/api";
import type { Job } from "@/lib/types";

interface InspectResult {
  kind: "csv" | "excel";
  sheets: string[];
  suggested_name: string;
  size_bytes: number;
}

export function UploadDatasetDialog({
  workspaceId,
  onUploaded,
  trigger,
  defaultOpen = false,
}: {
  workspaceId: string;
  onUploaded?: () => void;
  trigger?: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const [file, setFile] = useState<File | null>(null);
  const [inspect, setInspect] = useState<InspectResult | null>(null);
  const [sheet, setSheet] = useState<string>("");
  const [name, setName] = useState("");
  const [phase, setPhase] = useState<"idle" | "inspecting" | "uploading" | "processing" | "done">("idle");
  const [progress, setProgress] = useState(0);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setInspect(null);
      setName("");
      setSheet("");
      setError(null);
      setPhase("idle");
      setProgress(0);
      setJob(null);
    }
  }, [open]);

  useEffect(() => {
    if (phase !== "processing" || !job) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await api.get<Job>(`/jobs/${job.id}`);
        if (cancelled) return;
        setJob(next);
        setProgress(Math.max(5, next.progress));
        if (next.status === "completed") {
          setPhase("done");
          toast.success("Dataset processed", { description: "Profile and semantic model are ready for review." });
          onUploaded?.();
          const datasetId = (next.result?.dataset_id as string) || "";
          if (datasetId) router.push(`/app/datasets/${datasetId}`);
        } else if (next.status === "failed") {
          setPhase("idle");
          setError(next.error || "Processing failed. Try a different file or sheet.");
        } else {
          setTimeout(poll, 900);
        }
      } catch (err) {
        if (!cancelled) {
          setError(errorMessage(err));
          setPhase("idle");
        }
      }
    };
    const timer = setTimeout(poll, 700);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, job, onUploaded, router]);

  const handleFile = async (selected: File | null) => {
    setFile(selected);
    setInspect(null);
    setError(null);
    if (!selected) {
      setPhase("idle");
      return;
    }
    setPhase("inspecting");
    try {
      const form = new FormData();
      form.append("file", selected);
      const result = await api.upload<InspectResult>("/datasets/inspect", form);
      setInspect(result);
      setSheet(result.sheets[0] ?? "");
      setName(result.suggested_name);
      setPhase("idle");
    } catch (err) {
      setError(errorMessage(err));
      setFile(null);
      setPhase("idle");
    }
  };

  const submit = async () => {
    if (!file) return;
    setPhase("uploading");
    setError(null);
    setProgress(12);
    const form = new FormData();
    form.append("file", file);
    form.append("workspace_id", workspaceId);
    if (sheet) form.append("sheet_name", sheet);
    if (name) form.append("name", name);

    try {
      const response = await new Promise<{ dataset_id: string; job_id: string }>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/v1/datasets/upload");
        xhr.withCredentials = true;
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) setProgress(Math.max(12, Math.round((event.loaded / event.total) * 55)));
        };
        xhr.onload = () => {
          try {
            const body = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300 && body.success) resolve(body.data);
            else reject(new Error(body?.error?.message || "Upload failed"));
          } catch {
            reject(new Error("Upload failed"));
          }
        };
        xhr.onerror = () => reject(new Error("Network error during upload"));
        xhr.send(form);
      });
      setPhase("processing");
      setProgress(60);
      setJob({ id: response.job_id, job_type: "ingest_dataset", status: "queued", progress: 60 });
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
    }
  };

  const busy = phase === "uploading" || phase === "processing" || phase === "inspecting";

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="gradient">
            <Sparkles className="h-4 w-4" /> Upload dataset
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a dataset</DialogTitle>
          <DialogDescription>
            CSV or Excel. The original file is preserved, then profiled and modelled — nothing is overwritten.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-5 space-y-4">
          <UploadZone onSelect={handleFile} disabled={busy} value={file} />

          {inspect?.kind === "excel" && inspect.sheets.length > 1 && (
            <div className="space-y-1.5">
              <Label>Worksheet</Label>
              <Select value={sheet} onValueChange={setSheet} disabled={busy}>
                <SelectTrigger><SelectValue placeholder="Select sheet" /></SelectTrigger>
                <SelectContent>
                  {inspect.sheets.map((option) => (
                    <SelectItem key={option} value={option}>{option}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-faint">{inspect.sheets.length} worksheets detected.</p>
            </div>
          )}

          {inspect && (
            <div className="space-y-1.5">
              <Label htmlFor="dataset-name">Dataset name</Label>
              <Input id="dataset-name" value={name} onChange={(event) => setName(event.target.value)} disabled={busy} />
            </div>
          )}

          {error && (
            <div role="alert" className="rounded-xl border border-danger/25 bg-danger/[0.07] px-3 py-2.5 text-[12.5px] text-danger">
              {error}
            </div>
          )}

          {(phase === "uploading" || phase === "processing" || phase === "done") && (
            <div className="space-y-2 rounded-xl border border-line/10 bg-line/[0.03] p-3">
              <div className="flex items-center justify-between text-[12px]">
                <span className="flex items-center gap-1.5 text-muted">
                  {phase === "done" ? <CheckCircle2 className="h-3.5 w-3.5 text-success" /> : <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />}
                  {phase === "uploading" ? "Uploading file" : phase === "processing" ? job?.message || "Parsing, profiling and modelling" : "Ready"}
                </span>
                <span className="font-mono text-[11px] text-faint">{Math.round(progress)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-line/10">
                <div className="h-full rounded-full bg-brand-gradient transition-all duration-500" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}

          <div className="flex items-center justify-between gap-3 pt-1">
            <p className="flex items-center gap-1.5 text-[11px] text-faint">
              <FileSpreadsheet className="h-3.5 w-3.5" /> Max 50 MB · .csv, .xlsx
            </p>
            <Button onClick={submit} disabled={!file || busy} loading={busy} variant="gradient">
              Process dataset
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
