import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  BarChart3,
  Bot,
  Boxes,
  Database,
  FileSpreadsheet,
  Gauge,
  Layers,
  Lock,
  MessageSquareQuote,
  Network,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Table2,
  Zap,
} from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { HeroPreview } from "@/components/landing/hero-preview";
import { AnalystPreview } from "@/components/landing/analyst-preview";

const FEATURES = [
  {
    icon: ScanSearch,
    title: "Automatic data profiling",
    description:
      "Encoding detection, type inference, duplicates, IQR outliers and a quality score with a fully documented formula — no silent data changes.",
    tone: "text-brand",
  },
  {
    icon: Boxes,
    title: "Semantic intelligence",
    description:
      "Gemini proposes metrics, dimensions and time grains from real column statistics. Every definition is reviewable and versioned before use.",
    tone: "text-violet",
  },
  {
    icon: BarChart3,
    title: "Generated dashboards",
    description:
      "A strict JSON specification drives a trusted component registry — KPI cards, trends, heatmaps and tables rendered with Apache ECharts.",
    tone: "text-cyan",
  },
  {
    icon: Bot,
    title: "Conversational analytics",
    description:
      "Ask questions in plain language. The analyst plans the analysis, writes read-only SQL against your dataset and shows its work.",
    tone: "text-teal",
  },
  {
    icon: Network,
    title: "Hybrid RAG context",
    description:
      "Definitions, glossary notes and approved business context are embedded and retrieved with tenant-scoped filtering — never used for arithmetic.",
    tone: "text-magenta",
  },
  {
    icon: ShieldCheck,
    title: "Deterministic verification",
    description:
      "Every number in an answer is traced back to executed results, including derived shares and period deltas. Unsourced claims fail verification.",
    tone: "text-success",
  },
];

const STEPS = [
  { icon: FileSpreadsheet, title: "Ingest", copy: "Upload CSV or Excel. The pipeline validates content, detects encodings and preserves the original file." },
  { icon: Gauge, title: "Profile", copy: "Polars computes completeness, uniqueness, validity, consistency and outlier control in seconds." },
  { icon: Layers, title: "Model", copy: "A semantic model is proposed from your data and statistics. Review, edit and approve it." },
  { icon: MessageSquareQuote, title: "Analyse", copy: "Dashboards render from validated JSON; questions run through a stateful LangGraph workflow." },
];

export default function LandingPage() {
  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[720px] aurora" aria-hidden />
      <div className="pointer-events-none absolute inset-0 -z-10 grid-lines opacity-70" aria-hidden />

      {/* Navigation */}
      <header className="sticky top-0 z-40 border-b border-line/10 bg-canvas/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" aria-label="Agentic BI home">
            <Logo />
          </Link>
          <nav className="hidden items-center gap-8 text-[13px] text-muted md:flex" aria-label="Main">
            <a href="#platform" className="transition hover:text-ink">Platform</a>
            <a href="#workflow" className="transition hover:text-ink">Workflow</a>
            <a href="#analyst" className="transition hover:text-ink">AI analyst</a>
            <a href="#security" className="transition hover:text-ink">Security</a>
          </nav>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm" variant="gradient">
              <Link href="/register">
                Start free <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pb-20 pt-14 sm:px-6 lg:pt-20">
        <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
          <div className="animate-fade-up">
            <Badge tone="brand" className="mb-5 px-3 py-1">
              <Sparkles className="h-3 w-3" />
              AI business intelligence with SQL-backed answers
            </Badge>
            <h1 className="text-balance font-display text-[40px] font-semibold leading-[1.05] tracking-[-0.035em] text-ink sm:text-[54px]">
              Your business data.{" "}
              <span className="gradient-text">An intelligent new perspective.</span>
            </h1>
            <p className="mt-5 max-w-xl text-pretty text-[15px] leading-relaxed text-muted sm:text-[16px]">
              Upload a spreadsheet and get a profiled dataset, an approved semantic model, an interactive dashboard
              and an analyst you can cross-examine. Every number is computed in DuckDB — and every claim is verified.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild size="lg" variant="gradient">
                <Link href="/register">
                  Create your workspace <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/login">Explore the demo workspace</Link>
              </Button>
            </div>
            <dl className="mt-10 grid max-w-lg grid-cols-3 gap-4 border-t border-line/10 pt-6">
              {[
                { label: "Rows profiled", value: "9,266" },
                { label: "Verified answers", value: "100%" },
                { label: "Tenant isolation", value: "Org-scoped" },
              ].map((stat) => (
                <div key={stat.label}>
                  <dd className="kpi-value text-xl font-semibold text-ink">{stat.value}</dd>
                  <dt className="mt-1 text-[11px] uppercase tracking-[0.1em] text-faint">{stat.label}</dt>
                </div>
              ))}
            </dl>
          </div>
          <div className="animate-fade-up [animation-delay:120ms] lg:pl-4">
            <HeroPreview />
          </div>
        </div>
      </section>

      {/* Platform features */}
      <section id="platform" className="border-t border-line/10 bg-surface/35 py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">The platform</p>
            <h2 className="mt-3 text-balance font-display text-[32px] font-semibold tracking-[-0.03em] text-ink sm:text-[38px]">
              From raw spreadsheet to explainable insight
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Agentic BI combines a computational core with an agentic reasoning layer. The model decides what to
              analyse; the engine calculates; the verifier checks the evidence.
            </p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="glass glass-hover rounded-2xl p-5">
                <span className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border border-line/10 bg-line/[0.03] ${feature.tone}`}>
                  <feature.icon className="h-5 w-5" strokeWidth={1.6} />
                </span>
                <h3 className="mt-4 font-display text-[15px] font-semibold text-ink">{feature.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-muted">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Workflow */}
      <section id="workflow" className="py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet">How it works</p>
              <h2 className="mt-3 font-display text-[32px] font-semibold tracking-[-0.03em] text-ink sm:text-[38px]">
                Ingest → Profile → Understand → Analyse
              </h2>
            </div>
            <p className="max-w-sm text-[13px] leading-relaxed text-muted">
              A deterministic pipeline handles ingestion and computation. Agents orchestrate planning, retrieval and
              verification with bounded retries.
            </p>
          </div>
          <ol className="relative mt-10 grid gap-4 md:grid-cols-4">
            {STEPS.map((step, index) => (
              <li key={step.title} className="relative">
                <div className="glass h-full rounded-2xl p-5">
                  <div className="flex items-center justify-between">
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand">
                      <step.icon className="h-4 w-4" strokeWidth={1.8} />
                    </span>
                    <span className="font-mono text-[11px] text-faint">0{index + 1}</span>
                  </div>
                  <h3 className="mt-4 text-[14px] font-semibold text-ink">{step.title}</h3>
                  <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{step.copy}</p>
                </div>
                {index < STEPS.length - 1 && (
                  <ArrowRight className="absolute -right-3 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-faint md:block" aria-hidden />
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Analyst */}
      <section id="analyst" className="border-y border-line/10 bg-surface/35 py-20">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal">AI analyst</p>
            <h2 className="mt-3 text-balance font-display text-[32px] font-semibold tracking-[-0.03em] text-ink sm:text-[38px]">
              Ask the question. Inspect the SQL. Trust the answer.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-muted">
              The analyst is not a chatbot wrapped around a dashboard. It plans analyses, generates read-only SQL
              against your approved semantic model, decomposes changes by dimension and explains the result with
              cited evidence.
            </p>
            <ul className="mt-6 space-y-3">
              {[
                { icon: Zap, text: "Router, analyst, retrieval and verifier nodes coordinated by LangGraph." },
                { icon: Table2, text: "Result tables, inline charts and one-click SQL provenance." },
                { icon: Lock, text: "Policy-checked SQL: single SELECT, allowlisted tables, row limits, timeouts." },
                { icon: BadgeCheck, text: "Deterministic numeric grounding — not an LLM opinion about its own output." },
              ].map((item) => (
                <li key={item.text} className="flex items-start gap-2.5 text-[13.5px] leading-relaxed text-muted">
                  <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-brand" strokeWidth={1.8} />
                  {item.text}
                </li>
              ))}
            </ul>
          </div>
          <AnalystPreview />
        </div>
      </section>

      {/* Architecture / stack */}
      <section className="py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="glass rounded-2xl p-6 lg:col-span-1">
              <Database className="h-5 w-5 text-brand" />
              <h3 className="mt-4 font-display text-[17px] font-semibold text-ink">A computational core</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                Polars for ingestion and profiling. DuckDB for every analytical query. Parquet artefacts preserved
                per dataset version. PostgreSQL for application metadata and pgvector for context.
              </p>
              <div className="mt-5 flex flex-wrap gap-1.5">
                {["Polars", "DuckDB", "Parquet", "PostgreSQL", "pgvector"].map((tag) => (
                  <span key={tag} className="metric-pill">{tag}</span>
                ))}
              </div>
            </div>
            <div className="glass rounded-2xl p-6">
              <Bot className="h-5 w-5 text-violet" />
              <h3 className="mt-4 font-display text-[17px] font-semibold text-ink">An agentic reasoning layer</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                LangGraph orchestrates typed state across router, analyst, retrieval and verifier nodes. Gemini
                handles structured semantic proposals, SQL planning and narrative — never arithmetic.
              </p>
              <div className="mt-5 flex flex-wrap gap-1.5">
                {["LangGraph", "Gemini", "SQLGlot", "Pydantic", "Langfuse"].map((tag) => (
                  <span key={tag} className="metric-pill">{tag}</span>
                ))}
              </div>
            </div>
            <div className="glass rounded-2xl p-6">
              <Layers className="h-5 w-5 text-cyan" />
              <h3 className="mt-4 font-display text-[17px] font-semibold text-ink">A declarative front end</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                Dashboards are JSON, not generated code. Zod-validated specs render through a trusted component
                registry with Apache ECharts, cross-filtering and responsive TanStack tables.
              </p>
              <div className="mt-5 flex flex-wrap gap-1.5">
                {["Next.js", "TypeScript", "ECharts", "TanStack", "Tailwind"].map((tag) => (
                  <span key={tag} className="metric-pill">{tag}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Security */}
      <section id="security" className="border-t border-line/10 bg-surface/35 py-20">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-success">Security & governance</p>
            <h2 className="mt-3 font-display text-[32px] font-semibold tracking-[-0.03em] text-ink sm:text-[38px]">
              Built for data you cannot afford to leak
            </h2>
            <p className="mt-4 text-[14px] leading-relaxed text-muted">
              Tenant context is derived from the authenticated session on every request. Uploaded files are
              untrusted input. The AI never receives credentials, connection strings or unrestricted SQL access.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { title: "Organisation isolation", copy: "Every dataset, dashboard, conversation and chunk is scoped to an organisation and workspace." },
              { title: "Read-only execution", copy: "SQLGlot rejects DDL, DML, multiple statements, external file functions and unknown tables or columns." },
              { title: "Hardened uploads", copy: "Content validated by magic bytes and parsers, server-generated storage keys, 50 MB cap." },
              { title: "Auditability", copy: "Datasets, semantic models and dashboards are versioned; queries, agent runs and audit events are logged." },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl border border-line/10 bg-surface/60 p-4">
                <BadgeCheck className="h-4 w-4 text-success" />
                <h3 className="mt-2.5 text-[13px] font-semibold text-ink">{item.title}</h3>
                <p className="mt-1 text-[12px] leading-relaxed text-muted">{item.copy}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <div className="relative overflow-hidden rounded-3xl border border-line/12 bg-surface/70 p-10 text-center shadow-float backdrop-blur-xl">
            <div className="pointer-events-none absolute inset-0 bg-brand-gradient opacity-[0.09]" aria-hidden />
            <div className="relative">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">Start in minutes</p>
              <h2 className="mx-auto mt-3 max-w-2xl text-balance font-display text-[30px] font-semibold tracking-[-0.03em] text-ink sm:text-[36px]">
                Bring a spreadsheet. Leave with a dashboard and an analyst.
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-[14px] leading-relaxed text-muted">
                Create a workspace, load the synthetic retail demo in one click, approve the semantic model and ask
                your first question. No credit card, no SQL required.
              </p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                <Button asChild size="lg" variant="gradient">
                  <Link href="/register">
                    Create free workspace <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline">
                  <Link href="/login">Sign in</Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line/10 py-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Logo />
          </div>
          <nav className="flex flex-wrap items-center gap-6 text-[12px] text-muted" aria-label="Footer">
            <a href="#platform" className="transition hover:text-ink">Platform</a>
            <a href="#workflow" className="transition hover:text-ink">Workflow</a>
            <a href="#security" className="transition hover:text-ink">Security</a>
            <Link href="/login" className="transition hover:text-ink">Sign in</Link>
            <a href="/api/docs" className="transition hover:text-ink">API documentation</a>
          </nav>
          <p className="text-[11px] text-faint">© {new Date().getFullYear()} Agentic BI. Demonstration build.</p>
        </div>
      </footer>
    </div>
  );
}
