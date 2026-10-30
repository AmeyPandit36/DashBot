"use client";

import { useState } from "react";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function WorkspaceSwitcher() {
  const { workspace, workspaces, setWorkspaceId, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const router = useRouter();

  const create = async () => {
    if (name.trim().length < 2) {
      toast.error("Give the workspace a name");
      return;
    }
    setCreating(true);
    try {
      const created = await api.post<{ id: string; name: string }>("/workspaces", { name: name.trim() });
      await refresh();
      setWorkspaceId(created.id);
      setOpen(false);
      setName("");
      toast.success(`Switched to ${created.name}`);
      router.refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-2.5 rounded-xl border border-line/10 bg-surface/60 px-2.5 py-2 text-left transition hover:border-line/20"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-violet text-[11px] font-semibold text-white">
              {(workspace?.name ?? "W").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12px] font-medium text-ink">{workspace?.name ?? "No workspace"}</span>
              <span className="block text-[10px] text-faint">{workspaces.length} workspace{workspaces.length === 1 ? "" : "s"}</span>
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-faint" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[240px]">
          <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
          {workspaces.map((item) => (
            <DropdownMenuItem key={item.id} onSelect={() => { setWorkspaceId(item.id); router.refresh(); }}>
              <span className="flex w-full items-center gap-2">
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
                {item.id === workspace?.id && <Check className="h-3.5 w-3.5 text-brand" />}
              </span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={(event) => { event.preventDefault(); setOpen(true); }}>
            <Plus className="h-3.5 w-3.5" /> New workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create a workspace</DialogTitle>
            <DialogDescription>
              Workspaces isolate datasets, dashboards and conversations. Nothing is shared between them unless you move it.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-3">
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Retail — EMEA"
              onKeyDown={(event) => { if (event.key === "Enter") void create(); }}
            />
            <Button className="w-full" variant="gradient" onClick={create} loading={creating}>
              Create workspace
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
