export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  job_title?: string | null;
  preferences?: Record<string, unknown>;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  dataset_count?: number;
  dashboard_count?: number;
  created_at?: string;
}

export interface Session {
  user: SessionUser;
  organization: { id: string; name: string; slug: string; plan: string };
  role: "owner" | "admin" | "analyst" | "viewer";
  workspaces: Workspace[];
  token?: string;
}

export interface Dataset {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  file_name?: string | null;
  status: string;
  is_synthetic: boolean;
  row_count: number;
  column_count: number;
  quality_score?: number | null;
  active_version: number;
  version_count: number;
  created_at: string;
  updated_at: string;
  semantic_status?: string | null;
  semantic_model_id?: string | null;
  semantic_version?: number | null;
  active_version_detail?: DatasetVersion | null;
  dashboards?: { id: string; title: string; status: string; version: number }[];
}

export interface DatasetVersion {
  id: string;
  version_number: number;
  status: string;
  row_count: number;
  column_count: number;
  table_name: string;
  sheet_name?: string | null;
  encoding?: string | null;
  delimiter?: string | null;
  applied_transformations: { op: string; rows_before: number; rows_after: number }[];
  created_at: string;
  quality_score?: number | null;
  profile?: Profile;
  cleaning_plan?: { operations: { op: string; label: string }[]; auto_applied: boolean };
}

export interface ProfileColumn {
  name: string;
  inferred_type: string;
  ordinal_position: number;
  null_count: number;
  null_pct: number;
  unique_count: number;
  unique_pct: number;
  sample_values: (string | number | null)[];
  stats: Record<string, any>;
  top_values: { value: string | number | null; count: number }[];
  issues: string[];
}

export interface Profile {
  row_count: number;
  column_count: number;
  duplicate_rows: number;
  duplicate_pct: number;
  missing_cells: number;
  completeness_pct: number;
  quality_score: number;
  quality_components: Record<string, number>;
  quality_formula: { expression: string; definitions: Record<string, string> };
  columns: ProfileColumn[];
  categorical_columns: string[];
  date_columns: string[];
  date_ranges: Record<string, { min?: string; max?: string; span_days?: number }>;
  issues: { column: string | null; issue: string; detail: string }[];
  recommendations: { id: string; title: string; detail: string; impact: string; action: string }[];
  cleaning_plan: { operations: { op: string; label: string }[]; auto_applied: boolean };
}

export interface MetricDefinition {
  name: string;
  label: string;
  source_column: string;
  aggregation: string;
  format: string;
  description?: string;
  requires_approval?: boolean;
  numerator?: string | null;
  denominator?: string | null;
  confidence?: number;
}

export interface DimensionDefinition {
  name: string;
  label: string;
  source_column: string;
  data_type: string;
  description?: string;
  default_grain?: string | null;
  confirmed?: boolean;
  confidence?: number;
}

export interface SemanticDefinition {
  dataset_id: string;
  table_name: string;
  version: number;
  grain: string;
  generated_by?: string;
  metrics: MetricDefinition[];
  dimensions: DimensionDefinition[];
  time_dimensions: DimensionDefinition[];
  relationships: { from_column: string; to_column: string; type: string; confidence: number; note?: string }[];
  business_definitions: { term: string; definition: string }[];
}

export interface SemanticModel {
  id: string;
  dataset_id: string;
  version: number;
  status: string;
  generated_by: string;
  definition: SemanticDefinition;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
  dashboard_draft?: { id: string; title: string } | null;
}

export type WidgetType =
  | "kpi" | "line_chart" | "bar_chart" | "area_chart" | "pie_chart"
  | "donut_chart" | "scatter_chart" | "data_table" | "heatmap";

export interface Widget {
  id: string;
  type: WidgetType;
  title: string;
  description?: string;
  query_ref: string;
  encoding: Record<string, string | string[]>;
  layout: { x: number; y: number; w: number; h: number };
  interactions: { cross_filter: boolean; click_to_ask: boolean };
  options: {
    value_format: string;
    compare?: string;
    sort?: string;
    show_legend?: boolean;
    stacked?: boolean;
    palette?: string;
  };
}

export interface DashboardSpec {
  schema_version: string;
  dashboard_id?: string | null;
  title: string;
  description: string;
  dataset_id: string;
  semantic_model_version: number;
  generation_mode: string;
  layout: { columns: number; gap: number; density: string };
  filters: { id: string; label: string; field: string; type: "categorical" | "date_range"; default_value?: unknown }[];
  queries: Record<string, { metrics: string[]; group_by: string[]; grain?: string | null; filters: any[]; order_by?: any; limit: number }>;
  widgets: Widget[];
  metadata: Record<string, unknown>;
}

export interface DashboardSummary {
  id: string;
  workspace_id: string;
  dataset_id: string;
  title: string;
  description?: string | null;
  status: string;
  generation_mode: string;
  version?: number;
  version_count: number;
  widget_count: number;
  updated_at: string;
  created_at: string;
}

export interface DashboardDetail extends DashboardSummary {
  specification: DashboardSpec;
  semantic?: SemanticDefinition;
}

export interface WidgetData {
  widget_id: string;
  type: WidgetType;
  title: string;
  encoding: Record<string, string | string[]>;
  options: Record<string, any>;
  columns: string[];
  rows: (string | number | null)[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  sql: string;
  query_spec?: Record<string, any>;
  dataset_version_id?: string;
  comparison?: {
    previous_value: number | string | null;
    previous_start: string;
    previous_end: string;
    period_days: number;
    sql: string;
    row_count: number;
  } | null;
}

export interface VerificationCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface ChatEvidence {
  label: string;
  sql: string;
  columns: string[];
  row_count: number;
  status: string;
  error?: string | null;
  result?: { columns: string[]; rows: (string | number | null)[][]; row_count: number } | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  summary: string;
  intent: string;
  route: string;
  verification: { status: string; checks: VerificationCheck[]; issues: string[] };
  result?: { columns: string[]; rows: (string | number | null)[][]; row_count: number } | null;
  visualization?: { type: string; encoding: Record<string, string | string[]> } | null;
  insights: { title: string; detail: string; severity: string }[];
  follow_ups: string[];
  evidence: ChatEvidence[];
  context: { title: string; content: string; score: number }[];
  query_ids: string[];
  provenance: Record<string, any>;
  llm_used: boolean;
  errors?: string[];
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  content: Record<string, any>;
  verification_status?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  dataset_id?: string | null;
  message_count: number;
  updated_at: string;
  messages?: ConversationMessage[];
}

export interface Insight {
  id: string;
  dataset_id?: string | null;
  title: string;
  summary: string;
  insight_type: string;
  severity: string;
  evidence: Record<string, any>;
  verified: boolean;
  created_at: string;
}

export interface Job {
  id: string;
  job_type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  message?: string | null;
  error?: string | null;
  result?: Record<string, any>;
}

export interface PlatformConfig {
  app_name: string;
  version: string;
  currency_symbol: string;
  llm: { enabled: boolean; provider: string; model: string; note: string };
  uploads: { supported: string[]; max_mb: number };
  query_limits: { row_limit: number; timeout_seconds: number; memory_limit: string };
  demo_dataset: { name: string; synthetic: boolean; grain: string; definitions: Record<string, string> };
  features: Record<string, boolean>;
}
