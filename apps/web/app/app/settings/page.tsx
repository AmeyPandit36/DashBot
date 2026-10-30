"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import {
  Building2, Check, Copy, Database, FileText, KeyRound, Lock, Plus, Monitor, Moon, ShieldCheck,
  Sparkles, Sun, Trash2, UserPlus, Users,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import { cn } from "@/components/ui/utils";
import type { PlatformConfig } from "@/lib/types";

interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  joined_at: string;
}

interface DocumentItem {
  id: string;
  title: string;
  document_type: string;
  chunk_count: number;
  status: string;
  created_at: string;
}

interface SecurityInfo {
  sessions: { login_at: string | null; token_ttl_minutes: number; http_only_cookie: boolean; secure_cookie: boolean };
  ai: { llm_enabled: boolean; provider: string; model: string; tracing: boolean };
  storage: { backend: string };
  isolation: { scope: string; workspace_scoped_queries: boolean; audit_logging: boolean };
}

export default function SettingsPage() {
  const { session, workspace, workspaces, setWorkspaceId, refresh } = useAuth();
  const workspaceId = workspace?.id;
  const config = useApi<PlatformConfig>("/meta/config");
  const members = useApi<{ members: Member[]; invitations: { id: string; email: string; role: string; status: string; created_at: string }[] }>("/members");
  const security = useApi<SecurityInfo>("/settings/security");
  const documents = useApi<DocumentItem[]>(workspaceId ? `/documents?workspace_id=${workspaceId}` : null);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [profile, setProfile] = useState({ full_name: "", job_title: "" });
  const [savingProfile, setSavingProfile] = useState(false);
  const [workspaceForm, setWorkspaceForm] = useState({ name: "", description: "" });
  const [savingWorkspace, setSavingWorkspace] = useState(false);
  const [invite, setInvite] = useState({ email: "", role: "analyst" });
  const [inviting, setInviting] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [creating, setCreating] = useState(false);
  const [docForm, setDocForm] = useState({ title: "", content: "", document_type: "business_note" });
  const [savingDoc, setSavingDoc] = useState(false);

  useEffect(() => {
    if (session?.user) setProfile({ full_name: session.user.full_name ?? "", job_title: session.user.job_title ?? "" });
  }, [session?.user]);

  useEffect(() => {
    if (workspace) setWorkspaceForm({ name: workspace.name, description: workspace.description ?? "" });
  }, [workspace]);

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      await api.patch("/profile", profile);
      await refresh();
      toast.success("Profile updated");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingProfile(false);
    }
  };

  const saveWorkspace = async () => {
    if (!workspaceId) return;
    setSavingWorkspace(true);
    try {
      await api.patch(`/workspaces/${workspaceId}`, workspaceForm);
      await refresh();
      toast.success("Workspace updated");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingWorkspace(false);
    }
  };

  const createWorkspace = async () => {
    if (newWorkspaceName.trim().length < 2) {
      toast.error("Workspace name is too short");
      return;
    }
    setCreating(true);
    try {
      const created = await api.post<{ id: string; name: string }>("/workspaces", { name: newWorkspaceName.trim() });
      await refresh();
      setWorkspaceId(created.id);
      setNewWorkspaceName("");
      toast.success(`Workspace “${created.name}” created`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const sendInvite = async () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(invite.email)) {
      toast.error("Enter a valid email address");
      return;
    }
    setInviting(true);
    try {
      const result = await api.post<{ invited: boolean; note?: string }>("/members/invite", invite);
      await members.refresh();
      setInvite({ email: "", role: "analyst" });
      toast.success("Invitation recorded", { description: result.note ?? "They can now join the organisation." });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (membershipId: string, role: string) => {
    try {
      await api.patch(`/members/${membershipId}`, { role });
      await members.refresh();
      toast.success(`Role updated to ${role}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const addDocument = async () => {
    if (!workspaceId) return;
    if (docForm.title.trim().length < 2 || docForm.content.trim().length < 10) {
      toast.error("Add a title and at least a sentence of context");
      return;
    }
    setSavingDoc(true);
    try {
      await api.post("/documents", { workspace_id: workspaceId, ...docForm });
      await documents.refresh();
      setDocForm({ title: "", content: "", document_type: "business_note" });
      toast.success("Knowledge added", { description: "It is now retrievable by the analyst as business context." });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSavingDoc(false);
    }
  };

  const removeDocument = async (id: string) => {
    try {
      await api.del(`/documents/${id}`);
      await documents.refresh();
      toast.success("Document removed");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const copyId = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error("Clipboard access was blocked");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Configure"
        title="Settings"
        description="Profile, workspace, people, knowledge and platform status. Tenant isolation and audit logging are always on."
      />

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
          <TabsTrigger value="platform">Platform</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-4 space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <section className="glass rounded-2xl p-5">
              <h2 className="font-display text-[14px] font-semibold text-ink">Your details</h2>
              <p className="mt-0.5 text-[11.5px] text-muted">Shown on comments, audit entries and shared dashboards.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Full name</Label>
                  <Input value={profile.full_name} onChange={(event) => setProfile((current) => ({ ...current, full_name: event.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label>Job title</Label>
                  <Input value={profile.job_title} onChange={(event) => setProfile((current) => ({ ...current, job_title: event.target.value }))} placeholder="e.g. Head of Revenue Ops" />
                </div>
                <div className="space-y-1.5">
                  <Label>Email</Label>
                  <Input value={session?.user.email ?? ""} readOnly className="opacity-70" />
                </div>
                <div className="space-y-1.5">
                  <Label>Role</Label>
                  <Input value={titleCase(session?.role ?? "viewer")} readOnly className="opacity-70" />
                </div>
              </div>
              <Button className="mt-4" variant="gradient" onClick={saveProfile} loading={savingProfile}><Check className="h-4 w-4" /> Save changes</Button>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="font-display text-[14px] font-semibold text-ink">Appearance</h2>
              <p className="mt-0.5 text-[11.5px] text-muted">Follows your system preference by default.</p>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {[
                  { value: "light", label: "Light", icon: Sun },
                  { value: "dark", label: "Dark", icon: Moon },
                  { value: "system", label: "System", icon: Monitor },
                ].map((option) => {
                  const Icon = option.icon;
                  const active = mounted && theme === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTheme(option.value)}
                      className={cn(
                        "flex flex-col items-center gap-2 rounded-xl border px-2 py-4 text-[11.5px] transition",
                        active ? "border-brand/45 bg-brand/[0.07] text-ink" : "border-line/12 text-muted hover:border-line/25",
                      )}
                    >
                      <Icon className={cn("h-4 w-4", active && "text-brand")} />
                      {option.label}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 space-y-2 rounded-xl border border-line/10 bg-line/[0.02] p-3 text-[11.5px] text-muted">
                <p className="flex items-center gap-1.5"><Lock className="h-3.5 w-3.5 text-success" /> Session token stored in an http-only cookie</p>
                <p className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-success" /> Every query is scoped to {security.data?.isolation.scope ?? "organisation"}</p>
              </div>
            </section>
          </div>
        </TabsContent>

        <TabsContent value="workspace" className="mt-4 space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Building2 className="h-4 w-4 text-brand" /> {workspace?.name ?? "Workspace"}</h2>
              <div className="mt-4 space-y-3">
                <div className="space-y-1.5">
                  <Label>Workspace name</Label>
                  <Input value={workspaceForm.name} onChange={(event) => setWorkspaceForm((current) => ({ ...current, name: event.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label>Description</Label>
                  <Textarea rows={3} value={workspaceForm.description} onChange={(event) => setWorkspaceForm((current) => ({ ...current, description: event.target.value }))} placeholder="What decisions does this workspace support?" />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="gradient" onClick={saveWorkspace} loading={savingWorkspace}><Check className="h-4 w-4" /> Save workspace</Button>
                  <Button variant="ghost" size="sm" onClick={() => void copyId(workspaceId ?? "", "Workspace ID")}><Copy className="h-3.5 w-3.5" /> Copy ID</Button>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2 border-t border-line/10 pt-4 text-center">
                <div><p className="font-display text-[16px] font-semibold text-ink">{workspace?.dataset_count ?? 0}</p><p className="text-[10.5px] uppercase tracking-[0.1em] text-faint">datasets</p></div>
                <div><p className="font-display text-[16px] font-semibold text-ink">{workspace?.dashboard_count ?? 0}</p><p className="text-[10.5px] uppercase tracking-[0.1em] text-faint">dashboards</p></div>
                <div><p className="font-display text-[16px] font-semibold text-ink">{workspaces.length}</p><p className="text-[10.5px] uppercase tracking-[0.1em] text-faint">workspaces</p></div>
              </div>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="font-display text-[14px] font-semibold text-ink">Workspaces</h2>
              <div className="mt-3 space-y-1.5">
                {workspaces.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setWorkspaceId(item.id)}
                    className={cn("flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left transition",
                      item.id === workspaceId ? "border-brand/35 bg-brand/[0.06]" : "border-line/10 hover:border-line/25")}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[12.5px] font-medium text-ink">{item.name}</span>
                      <span className="text-[10.5px] text-faint">{item.dataset_count ?? 0} datasets · {item.dashboard_count ?? 0} dashboards</span>
                    </span>
                    {item.id === workspaceId && <Check className="h-3.5 w-3.5 text-brand" />}
                  </button>
                ))}
              </div>
              <div className="mt-4 space-y-2 border-t border-line/10 pt-4">
                <Label>Create workspace</Label>
                <div className="flex gap-2">
                  <Input value={newWorkspaceName} onChange={(event) => setNewWorkspaceName(event.target.value)} placeholder="e.g. EU Expansion" />
                  <Button variant="outline" size="icon" onClick={createWorkspace} loading={creating} aria-label="Create workspace"><Plus className="h-4 w-4" /></Button>
                </div>
              </div>
            </section>
          </div>
        </TabsContent>

        <TabsContent value="people" className="mt-4 space-y-4">
          <section className="glass rounded-2xl p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Users className="h-4 w-4 text-brand" /> Members</h2>
                <p className="mt-0.5 text-[11.5px] text-muted">Owners and admins manage access. Analysts build; viewers read.</p>
              </div>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="gradient" size="sm"><UserPlus className="h-3.5 w-3.5" /> Invite</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Invite a teammate</DialogTitle>
                    <DialogDescription>Existing users are added straight away. New addresses receive a pending invitation.</DialogDescription>
                  </DialogHeader>
                  <div className="mt-4 space-y-3">
                    <div className="space-y-1.5">
                      <Label>Email</Label>
                      <Input type="email" value={invite.email} onChange={(event) => setInvite((current) => ({ ...current, email: event.target.value }))} placeholder="colleague@company.com" />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Role</Label>
                      <Select value={invite.role} onValueChange={(value) => setInvite((current) => ({ ...current, role: value }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["admin", "analyst", "viewer"].map((role) => <SelectItem key={role} value={role}>{titleCase(role)}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button className="w-full" variant="gradient" onClick={sendInvite} loading={inviting}>Send invitation</Button>
                  </div>
                </DialogContent>
              </Dialog>
            </div>

            <div className="mt-4 overflow-hidden rounded-xl border border-line/10">
              <table className="w-full text-left text-[12.5px]">
                <thead className="bg-line/[0.04] text-[10.5px] uppercase tracking-wider text-faint">
                  <tr><th className="px-3 py-2 font-medium">Person</th><th className="px-3 py-2 font-medium">Role</th><th className="px-3 py-2 font-medium">Joined</th><th className="px-3 py-2 font-medium">Status</th></tr>
                </thead>
                <tbody>
                  {(members.data?.members ?? []).map((member) => (
                    <tr key={member.id} className="border-t border-line/[0.07]">
                      <td className="px-3 py-2.5">
                        <p className="font-medium text-ink">{member.full_name}</p>
                        <p className="text-[11px] text-muted">{member.email}</p>
                      </td>
                      <td className="px-3 py-2.5">
                        {member.role === "owner" ? (
                          <Badge tone="brand">Owner</Badge>
                        ) : (
                          <Select value={member.role} onValueChange={(value) => void changeRole(member.id, value)}>
                            <SelectTrigger className="h-7 w-[110px] text-[11.5px]"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {["admin", "analyst", "viewer"].map((role) => <SelectItem key={role} value={role}>{titleCase(role)}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-muted">{formatDate(member.joined_at)}</td>
                      <td className="px-3 py-2.5"><Badge tone={member.status === "active" ? "success" : "neutral"}>{member.status}</Badge></td>
                    </tr>
                  ))}
                  {members.loading && <tr><td colSpan={4} className="px-3 py-8 text-center text-muted">Loading members…</td></tr>}
                </tbody>
              </table>
            </div>

            {(members.data?.invitations ?? []).length > 0 && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Pending invitations</p>
                {(members.data?.invitations ?? []).map((invitation) => (
                  <div key={invitation.id} className="flex items-center justify-between rounded-lg border border-dashed border-line/15 px-3 py-2 text-[12px]">
                    <span className="text-ink">{invitation.email}</span>
                    <span className="flex items-center gap-2 text-[11px] text-muted"><Badge tone="neutral">{invitation.role}</Badge>{relativeTime(invitation.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </TabsContent>

        <TabsContent value="knowledge" className="mt-4 space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Sparkles className="h-4 w-4 text-violet" /> Add business context</h2>
              <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">
                Definitions, pricing policy, regional notes. Retrieved with embeddings and cited by the analyst — never used to compute numbers.
              </p>
              <div className="mt-4 space-y-3">
                <div className="space-y-1.5">
                  <Label>Title</Label>
                  <Input value={docForm.title} onChange={(event) => setDocForm((current) => ({ ...current, title: event.target.value }))} placeholder="e.g. Discount policy FY26" />
                </div>
                <div className="space-y-1.5">
                  <Label>Type</Label>
                  <Select value={docForm.document_type} onValueChange={(value) => setDocForm((current) => ({ ...current, document_type: value }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="business_note">Business note</SelectItem>
                      <SelectItem value="glossary">Glossary</SelectItem>
                      <SelectItem value="policy">Policy</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Content</Label>
                  <Textarea rows={6} value={docForm.content} onChange={(event) => setDocForm((current) => ({ ...current, content: event.target.value }))} placeholder="Explain how the team defines revenue, returns, or seasonal adjustments…" />
                </div>
                <Button variant="gradient" onClick={addDocument} loading={savingDoc}><Plus className="h-4 w-4" /> Index document</Button>
              </div>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><FileText className="h-4 w-4 text-cyan" /> Knowledge base</h2>
              <div className="mt-3 space-y-2">
                {(documents.data ?? []).map((document) => (
                  <div key={document.id} className="flex items-center justify-between gap-2 rounded-xl border border-line/10 px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-[12.5px] font-medium text-ink">{document.title}</p>
                      <p className="text-[10.5px] text-faint">{titleCase(document.document_type)} · {document.chunk_count} chunks · {relativeTime(document.created_at)}</p>
                    </div>
                    <Button variant="ghost" size="icon-sm" onClick={() => void removeDocument(document.id)} aria-label={`Delete ${document.title}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                ))}
                {!documents.loading && (documents.data ?? []).length === 0 && (
                  <p className="rounded-xl border border-dashed border-line/15 px-3 py-8 text-center text-[12px] text-muted">
                    No documents yet. Semantic-model definitions are already searchable; add notes for team-specific context.
                  </p>
                )}
              </div>
            </section>
          </div>
        </TabsContent>

        <TabsContent value="platform" className="mt-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Sparkles className="h-4 w-4 text-brand" /> AI runtime</h2>
              <dl className="mt-3 space-y-2 text-[12px]">
                <Row label="Status" value={security.data?.ai.llm_enabled ? "Gemini configured" : "Deterministic engine"} />
                <Row label="Provider" value={security.data?.ai.provider ?? "—"} />
                <Row label="Model" value={security.data?.ai.model ?? "—"} />
                <Row label="Tracing" value={security.data?.ai.tracing ? "Langfuse enabled" : "Off"} />
              </dl>
              <p className="mt-3 rounded-lg bg-line/[0.03] p-2.5 text-[11px] leading-relaxed text-muted">
                {config.data?.llm.note ?? "Platform configuration is loading."}
              </p>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Database className="h-4 w-4 text-cyan" /> Query guardrails</h2>
              <dl className="mt-3 space-y-2 text-[12px]">
                <Row label="Row limit" value={String(config.data?.query_limits.row_limit ?? "—")} />
                <Row label="Timeout" value={`${config.data?.query_limits.timeout_seconds ?? "—"}s`} />
                <Row label="Memory" value={config.data?.query_limits.memory_limit ?? "—"} />
                <Row label="Uploads" value={(config.data?.uploads.supported ?? []).join(", ")} />
                <Row label="Max upload" value={`${config.data?.uploads.max_mb ?? "—"} MB`} />
              </dl>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><KeyRound className="h-4 w-4 text-violet" /> Session & isolation</h2>
              <dl className="mt-3 space-y-2 text-[12px]">
                <Row label="Last login" value={security.data?.sessions.login_at ? formatDate(security.data.sessions.login_at, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"} />
                <Row label="Token TTL" value={`${security.data?.sessions.token_ttl_minutes ?? "—"} minutes`} />
                <Row label="Cookie" value={security.data?.sessions.http_only_cookie ? "http-only" : "token header"} />
                <Row label="Storage" value={security.data?.storage.backend ?? "—"} />
                <Row label="Audit logging" value={security.data?.isolation.audit_logging ? "Enabled" : "Off"} />
              </dl>
            </section>

            <section className="glass rounded-2xl p-5">
              <h2 className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Building2 className="h-4 w-4 text-brand" /> Tenant</h2>
              <dl className="mt-3 space-y-2 text-[12px]">
                <Row label="Organisation" value={session?.organization.name ?? "—"} />
                <Row label="Plan" value={titleCase(session?.organization.plan ?? "—")} />
                <Row label="Scope" value={security.data?.isolation.scope ?? "organisation"} />
                <Row label="App version" value={config.data?.version ?? "—"} />
              </dl>
            </section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/[0.07] pb-1.5 last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
