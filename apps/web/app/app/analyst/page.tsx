"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowUp, Bot, BookOpen, Check, ChevronDown, Copy, Database, Lightbulb, Loader2,
  MessageSquarePlus, Plus, Sparkles, ThumbsDown, ThumbsUp, Trash2, TrendingUp, User,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RichText } from "@/components/common/rich-text";
import { SQLViewer } from "@/components/common/sql-viewer";
import { VerificationBadge } from "@/components/common/verification-badge";
import { DataTable } from "@/components/common/data-table";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, relativeTime, titleCase } from "@/lib/format";
import { cn } from "@/components/ui/utils";
import type { ChatResponse, Conversation, ConversationMessage, Dataset, Workspace } from "@/lib/types";

type Turn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  verification_status?: string | null;
  created_at?: string;
  pending?: boolean;
  error?: string;
};

const SUGGESTIONS = [
  "What is total revenue?",
  "Which region generated the highest revenue?",
  "What are the monthly sales trends?",
  "Why did revenue decrease recently?",
  "How many unique customers do we have?",
  "What does average order value mean?",
];

export default function AnalystPage() {
  const { workspace, workspaces, setWorkspaceId } = useAuth();
  const workspaceId = workspace?.id;
  const datasets = useApi<Dataset[]>(workspaceId ? `/datasets?workspace_id=${workspaceId}` : null);
  const conversations = useApi<Conversation[]>(workspaceId ? `/conversations?workspace_id=${workspaceId}` : null);

  const [datasetId, setDatasetId] = useState<string>("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const datasetList = datasets.data ?? [];
  const selected = datasetList.find((dataset) => dataset.id === datasetId);

  // Preselect the dataset from ?datasetId= or the first one available.
  useEffect(() => {
    if (datasetId) return;
    if (typeof window !== "undefined") {
      const param = new URLSearchParams(window.location.search).get("datasetId");
      if (param && datasetList.some((dataset) => dataset.id === param)) {
        setDatasetId(param);
        return;
      }
    }
    if (datasetList.length) setDatasetId(datasetList[0].id);
  }, [datasetList, datasetId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, sending]);

  const openConversation = useCallback(async (id: string, datasetHint?: string | null) => {
    setHistoryLoading(true);
    setConversationId(id);
    setHistoryOpen(false);
    try {
      const detail = await api.get<Conversation & { messages?: ConversationMessage[] }>(`/conversations/${id}`);
      if (datasetHint) setDatasetId(datasetHint);
      setTurns(
        (detail.messages ?? []).map((message) => ({
          id: message.id,
          role: message.role,
          text: message.text,
          verification_status: message.verification_status,
          response: message.role === "assistant" ? (message.content as unknown as ChatResponse) : undefined,
          created_at: message.created_at,
        })),
      );
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const conversationParam = params.get("c");
    const questionParam = params.get("q");
    if (conversationParam) {
      void openConversation(conversationParam);
      return;
    }
    if (questionParam) {
      setInput(questionParam);
      window.history.replaceState({}, "", "/app/analyst");
    }
  }, [openConversation]);


  const startNew = () => {
    setConversationId(null);
    setTurns([]);
    setInput("");
    setHistoryOpen(false);
    textareaRef.current?.focus();
  };

  const send = async (question?: string) => {
    const text = (question ?? input).trim();
    if (!text || sending) return;
    if (!workspaceId || !datasetId) {
      toast.error("Choose a dataset first");
      return;
    }
    const localId = `local-${Date.now()}`;
    setTurns((current) => [
      ...current,
      { id: `${localId}-user`, role: "user", text, created_at: new Date().toISOString() },
      { id: `${localId}-assistant`, role: "assistant", text: "", pending: true },
    ]);
    setInput("");
    setSending(true);
    try {
      const response = await api.post<ChatResponse>("/chat", {
        workspace_id: workspaceId,
        dataset_id: datasetId,
        conversation_id: conversationId,
        question: text,
      });
      setConversationId(response.conversation_id);
      setTurns((current) => {
        const next = [...current];
        const index = next.findIndex((turn) => turn.id === `${localId}-assistant`);
        if (index >= 0) {
          next[index] = {
            id: response.message_id,
            role: "assistant",
            text: response.answer,
            response,
            verification_status: response.verification?.status,
            created_at: new Date().toISOString(),
          };
        }
        return next;
      });
      void conversations.refresh();
    } catch (err) {
      const message = errorMessage(err);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === `${localId}-assistant` ? { ...turn, pending: false, error: message, text: "" } : turn,
        ),
      );
      toast.error(message);
    } finally {
      setSending(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  };

  const rate = async (messageId: string, feedback: "helpful" | "not_helpful") => {
    if (!conversationId) return;
    try {
      await api.post(`/chat/${conversationId}/feedback`, { message_id: messageId, feedback });
      toast.success(feedback === "helpful" ? "Marked as helpful" : "Thanks — flagged for review");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const removeConversation = async (id: string) => {
    try {
      await api.del(`/conversations/${id}`);
      if (id === conversationId) startNew();
      void conversations.refresh();
      toast.success("Conversation deleted");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  return (
    <div className="flex h-[calc(100vh-9.5rem)] min-h-[560px] gap-4">
      {/* History rail */}
      <aside className={cn("glass hidden w-[248px] shrink-0 flex-col rounded-2xl p-3 lg:flex")}>
        <Button variant="outline" size="sm" className="w-full justify-start" onClick={startNew}>
          <MessageSquarePlus className="h-4 w-4" /> New analysis
        </Button>
        <p className="mt-4 px-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-faint">Recent</p>
        <div className="mt-2 flex-1 space-y-1 overflow-y-auto pr-0.5">
          {conversations.loading && <div className="h-16 skeleton rounded-lg" />}
          {!conversations.loading && (conversations.data ?? []).length === 0 && (
            <p className="px-1 py-6 text-[11.5px] leading-relaxed text-faint">
              Your questions appear here. Every answer keeps its SQL, row counts and verification checks.
            </p>
          )}
          {(conversations.data ?? []).map((conversation) => (
            <div
              key={conversation.id}
              className={cn(
                "group flex items-center gap-1 rounded-lg border border-transparent px-2 py-2 transition hover:bg-line/[0.05]",
                conversation.id === conversationId && "border-brand/25 bg-brand/[0.06]",
              )}
            >
              <button
                type="button"
                onClick={() => void openConversation(conversation.id, conversation.dataset_id)}
                className="min-w-0 flex-1 text-left"
              >
                <p className="truncate text-[12px] font-medium text-ink">{conversation.title}</p>
                <p className="text-[10.5px] text-faint">{conversation.message_count} msgs · {relativeTime(conversation.updated_at)}</p>
              </button>
              <button
                type="button"
                onClick={() => void removeConversation(conversation.id)}
                aria-label={`Delete ${conversation.title}`}
                className="rounded p-1 text-faint opacity-0 transition hover:bg-danger/10 hover:text-danger group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
        {workspaces.length > 1 && workspaceId && (
          <div className="mt-2 border-t border-line/10 pt-2">
            <Select value={workspaceId} onValueChange={setWorkspaceId}>
              <SelectTrigger className="h-8 text-[11.5px]"><SelectValue /></SelectTrigger>
              <SelectContent>{workspaces.map((item: Workspace) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        )}
      </aside>

      {/* Thread */}
      <section className="glass flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl">
        <header className="flex items-center gap-3 border-b border-line/10 px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-violet text-white shadow-glow">
            <Bot className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-[13.5px] font-semibold text-ink">AI Analyst</p>
            <p className="truncate text-[11px] text-muted">
              Text-to-SQL over DuckDB · every number traced to an executed query
            </p>
          </div>
          <div className="w-[190px]">
            <Select value={datasetId} onValueChange={(value) => { setDatasetId(value); setConversationId(null); setTurns([]); }}>
              <SelectTrigger className="h-8 text-[11.5px]"><SelectValue placeholder="Select dataset" /></SelectTrigger>
              <SelectContent>
                {datasetList.map((dataset) => (
                  <SelectItem key={dataset.id} value={dataset.id}>{dataset.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5">
          {historyLoading ? (
            <div className="space-y-3">
              <div className="h-20 skeleton rounded-xl" />
              <div className="h-40 skeleton rounded-xl" />
            </div>
          ) : turns.length === 0 ? (
            <EmptyThread
              datasetName={selected?.name}
              onPick={(question) => void send(question)}
              hasDataset={Boolean(datasetId)}
              onOpenHistory={() => setHistoryOpen((open) => !open)}
            />
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              {turns.map((turn) => (
                <TurnView key={turn.id} turn={turn} onFollowUp={(question) => void send(question)} onRate={rate} datasetId={datasetId} />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-line/10 bg-surface/40 px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2 rounded-2xl border border-line/12 bg-surface/80 p-2 shadow-sm focus-within:border-brand/40">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
                rows={1}
                placeholder="Ask about revenue, regions, trends, definitions…"
                className="max-h-32 min-h-[38px] flex-1 resize-none bg-transparent px-2 py-2 text-[13px] text-ink outline-none placeholder:text-faint"
                aria-label="Ask the AI analyst"
              />
              <Button
                variant="gradient"
                size="icon"
                onClick={() => void send()}
                disabled={!input.trim() || sending || !datasetId}
                aria-label="Send question"
              >
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
              </Button>
            </div>
            <p className="mt-1.5 px-1 text-[10.5px] text-faint">
              Enter to send · Shift+Enter for a new line. Answers are computed from your data, not generated prose.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function EmptyThread({
  datasetName,
  onPick,
  hasDataset,
  onOpenHistory,
}: {
  datasetName?: string;
  onPick: (question: string) => void;
  hasDataset: boolean;
  onOpenHistory: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center justify-center py-8 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand/20 via-violet/15 to-cyan/10 text-brand">
        <Sparkles className="h-6 w-6" />
      </span>
      <h2 className="mt-4 font-display text-[20px] font-semibold tracking-tight text-ink">
        Ask anything about {datasetName ?? "your data"}
      </h2>
      <p className="mt-1.5 max-w-md text-[12.5px] leading-relaxed text-muted">
        The analyst plans a question, writes validated SQL, executes it in DuckDB and verifies every number against
        the returned rows. Business definitions come from your semantic model and knowledge base.
      </p>
      {!hasDataset && (
        <div className="mt-4 rounded-xl border border-warning/25 bg-warning/[0.08] px-4 py-3 text-[12px] text-ink">
          No datasets yet.{" "}
          <Link href="/app/datasets" className="font-medium text-brand hover:underline">Load the retail demo</Link>{" "}
          to get started.
        </div>
      )}
      <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            className="group flex items-center justify-between gap-2 rounded-xl border border-line/12 bg-surface/50 px-3.5 py-2.5 text-left text-[12.5px] text-ink transition hover:border-brand/35 hover:bg-brand/[0.05]"
          >
            <span>{question}</span>
            <ArrowUp className="h-3.5 w-3.5 shrink-0 rotate-45 text-faint transition group-hover:text-brand" />
          </button>
        ))}
      </div>
      <button type="button" onClick={onOpenHistory} className="mt-4 text-[11.5px] font-medium text-muted underline-offset-4 hover:text-brand hover:underline lg:hidden">
        Browse past conversations
      </button>
    </div>
  );
}

function TurnView({
  turn,
  onFollowUp,
  onRate,
  datasetId,
}: {
  turn: Turn;
  onFollowUp: (question: string) => void;
  onRate: (messageId: string, feedback: "helpful" | "not_helpful") => void;
  datasetId: string;
}) {
  const [showAllRows, setShowAllRows] = useState(false);
  const [copied, setCopied] = useState(false);

  const response = turn.response;
  const result = response?.result;
  const rows = result?.rows ?? [];
  const visibleRows = showAllRows ? rows : rows.slice(0, 12);

  const columns = useMemo(
    () =>
      (result?.columns ?? []).map((column) => ({
        accessorKey: column,
        header: titleCase(column),
        cell: ({ getValue }: { getValue: () => unknown }) => {
          const value = getValue();
          if (value === null || value === undefined) return <span className="text-faint">—</span>;
          if (typeof value === "number") {
            return <span className="tabular-nums">{new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value)}</span>;
          }
          return <span>{String(value)}</span>;
        },
      })),
    [result?.columns],
  );

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(turn.text);
      setCopied(true);
      toast.success("Answer copied");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Clipboard access was blocked");
    }
  };

  if (turn.role === "user") {
    return (
      <div className="flex justify-end gap-2.5">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-brand to-brand-strong px-4 py-2.5 text-[13px] leading-relaxed text-white shadow-glow">
          {turn.text}
        </div>
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-line/[0.08] text-muted">
          <User className="h-3.5 w-3.5" />
        </span>
      </div>
    );
  }

  if (turn.pending) {
    return (
      <div className="flex gap-2.5">
        <AssistantAvatar />
        <div className="flex-1 rounded-2xl rounded-tl-md border border-line/10 bg-surface/60 px-4 py-3">
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
            Planning the question, writing SQL and verifying results…
          </div>
          <div className="mt-3 space-y-2">
            <div className="h-2.5 w-3/4 skeleton rounded" />
            <div className="h-2.5 w-1/2 skeleton rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (turn.error) {
    return (
      <div className="flex gap-2.5">
        <AssistantAvatar />
        <div className="flex-1 rounded-2xl rounded-tl-md border border-danger/25 bg-danger/[0.06] px-4 py-3 text-[12.5px] text-ink">
          <p className="font-medium text-danger">The analyst could not complete this request</p>
          <p className="mt-1 text-muted">{turn.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="rounded-2xl rounded-tl-md border border-line/10 bg-surface/60 px-4 py-3">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <VerificationBadge status={turn.verification_status} checks={response?.verification?.checks} />
            {response?.route && <Badge tone="neutral">{titleCase(response.route)}</Badge>}
            {typeof response?.llm_used === "boolean" && (
              <Badge tone={response.llm_used ? "brand" : "neutral"}>{response.llm_used ? "Gemini reasoning" : "Deterministic engine"}</Badge>
            )}
            {result && <span className="text-[10.5px] text-faint">{result.row_count} rows · {response?.evidence?.[0]?.status}</span>}
          </div>
          <RichText text={turn.text} />

          {response?.visualization && result && rows.length > 0 && (
            <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-brand/[0.05] px-2.5 py-1.5 text-[11px] text-brand">
              <TrendingUp className="h-3.5 w-3.5" />
              Best shown as a {titleCase(response.visualization.type)} —{" "}
              <Link href={`/app/dashboards`} className="font-medium underline underline-offset-2">add it to a dashboard</Link>
            </div>
          )}
        </div>

        {result && rows.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-line/10 bg-surface/40">
            <DataTable columns={columns} data={visibleRows} compact maxHeight={showAllRows ? 420 : undefined} />
            {rows.length > 12 && (
              <button
                type="button"
                onClick={() => setShowAllRows((value) => !value)}
                className="flex w-full items-center justify-center gap-1 border-t border-line/10 py-2 text-[11.5px] font-medium text-muted transition hover:bg-line/[0.04] hover:text-ink"
              >
                <ChevronDown className={cn("h-3.5 w-3.5 transition", showAllRows && "rotate-180")} />
                {showAllRows ? "Show fewer rows" : `Show all ${rows.length} rows`}
              </button>
            )}
          </div>
        )}

        {(response?.evidence ?? []).length > 0 && (
          <div className="space-y-1.5">
            {(response?.evidence ?? []).map((evidence, index) => (
              <SQLViewer
                key={index}
                sql={evidence.sql}
                label={evidence.label || `Query ${index + 1}`}
                meta={
                  <span className="flex items-center gap-1.5 text-[10.5px] text-[#9AA3C2]">
                    <Database className="h-3 w-3" />
                    {evidence.row_count} rows
                    <span className={cn("rounded px-1 py-0.5", evidence.status === "success" ? "bg-success/20 text-success" : "bg-warning/20 text-warning")}>
                      {evidence.status}
                    </span>
                  </span>
                }
              />
            ))}
          </div>
        )}

        {(response?.context ?? []).length > 0 && (
          <details className="group rounded-xl border border-line/10 bg-line/[0.02] px-3 py-2">
            <summary className="flex cursor-pointer items-center gap-1.5 text-[11.5px] font-medium text-muted">
              <BookOpen className="h-3.5 w-3.5 text-violet" />
              Business context retrieved ({(response?.context ?? []).length})
              <ChevronDown className="ml-auto h-3.5 w-3.5 transition group-open:rotate-180" />
            </summary>
            <ul className="mt-2 space-y-2">
              {(response?.context ?? []).map((chunk, index) => (
                <li key={index} className="rounded-lg bg-surface/60 px-2.5 py-2">
                  <p className="text-[11px] font-medium text-ink">{chunk.title} <span className="text-faint">· {chunk.score.toFixed(2)}</span></p>
                  <p className="mt-0.5 line-clamp-3 text-[11px] leading-relaxed text-muted">{chunk.content}</p>
                </li>
              ))}
            </ul>
          </details>
        )}

        {(response?.insights ?? []).length > 0 && (
          <div className="space-y-1.5">
            {(response?.insights ?? []).map((insight, index) => (
              <div key={index} className="flex gap-2 rounded-xl border border-violet/20 bg-violet/[0.05] px-3 py-2">
                <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet" />
                <div>
                  <p className="text-[12px] font-medium text-ink">{insight.title}</p>
                  <p className="text-[11px] leading-relaxed text-muted">{insight.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5">
          {(response?.follow_ups ?? []).map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onFollowUp(question)}
              className="rounded-full border border-line/12 px-2.5 py-1 text-[11px] text-muted transition hover:border-brand/35 hover:text-brand"
            >
              {question}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-0.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={copyAnswer} aria-label="Copy answer">
                  {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Copy answer</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={() => onRate(turn.id, "helpful")} aria-label="Mark helpful">
                  <ThumbsUp className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Helpful</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={() => onRate(turn.id, "not_helpful")} aria-label="Mark not helpful">
                  <ThumbsDown className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Not helpful</TooltipContent>
            </Tooltip>
            <Link href={`/app/datasets/${datasetId}`} className="ml-1 text-[10.5px] text-faint hover:text-brand">
              <span className="flex items-center gap-1"><Plus className="h-3 w-3" /> dataset</span>
            </Link>
          </div>
        </div>
        {turn.created_at && <p className="text-[10px] text-faint">{formatDateTime(turn.created_at)}</p>}
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-violet text-white">
      <Bot className="h-3.5 w-3.5" />
    </span>
  );
}
