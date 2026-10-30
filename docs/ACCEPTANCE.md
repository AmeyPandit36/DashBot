# Acceptance criteria — status

The completion bar from the Engineering Project Bible §21, with the evidence for each item.
“Proven by” names an executed test or a reproducible command; anything conditional is stated as such.

| ID | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| **AC-01** | User can register and authenticate | ✅ Met | `test_api_contract.py::test_register_login_me_logout`, `::test_cookie_session_authenticates_browser_requests`, `::test_password_reset_flow`; UI `/register`, `/login`, `/forgot-password`, `/reset-password`; http-only cookie + bearer support |
| **AC-02** | User can create a workspace | ✅ Met | Registration creates a default workspace; `POST /workspaces` covered by `test_workspaces_and_members`, `test_workspace_scoping_inside_same_organization`; UI workspace switcher + `/app/settings → Workspace` |
| **AC-03** | User can upload CSV and XLSX files | ✅ Met | `test_ingestion.py::test_csv_upload_profiles_and_registers_versions`, `::test_excel_sheet_selection_and_inspect` (multi-sheet selection), `::test_upload_validation`; UI `UploadDatasetDialog` with inspect → sheet → progress |
| **AC-04** | Application detects supported data types | ✅ Met | Profiling infers integer/decimal/boolean/date/text per column (`profile.columns[].inferred_type`), asserted in `test_csv_upload_…`; semantic dimension `data_type` derived from it |
| **AC-05** | Application generates a data quality profile | ✅ Met | `test_quality_score_matches_documented_formula` recomputes the weighted formula from components; UI quality dial, issues, recommendations, cleaning plan |
| **AC-06** | Gemini proposes a semantic model | ⚠️ Implemented, **not exercised with a live key** | Gemini path: `semantic/inference.py::refine_with_llm` (structured JSON, validated against real columns). With no key, the deterministic proposal is used and the UI states the current provider truthfully (`/meta/config` → `llm.enabled=false`). Evidence for the proposal itself: `test_semantic_model.py::test_proposal_is_grounded_in_real_columns`. **Requires `GEMINI_API_KEY` to demonstrate the Gemini variant.** |
| **AC-07** | User can edit and approve semantic definitions | ✅ Met | `test_semantic_model.py::test_approval_indexes_glossary_and_creates_draft_dashboard`, `::test_editing_an_approved_model_creates_a_review_version`, `::test_invalid_metrics_are_dropped_with_a_report`, `::test_rejecting_a_model`; UI `/app/semantic/[id]` (metrics, dimensions, time, glossary tabs) |
| **AC-08** | Dashboard planner produces valid JSON | ✅ Met | `test_dashboards.py::test_automatic_generation_produces_valid_spec`; strict Pydantic contract in `dashboards/schema.py`; unknown widget types and dangling refs rejected (`::test_unknown_widget_type_is_rejected_at_validation`, `::test_dangling_query_reference_is_rejected`) |
| **AC-09** | Automatic mode renders the dashboard | ✅ Met | `POST /dashboards/generate {mode:"automatic"}` → `status=published`, 10 widgets; UI `/app/dashboards/[id]` renders through the trusted registry. `test_review_mode_creates_draft` covers the counterpart |
| **AC-10** | Review mode supports approval and editing | ✅ Met | Review mode produces `status=draft`; UI edit mode (retitle, width, add/remove widget), save creates a new immutable version, publish switches the active version — `test_dashboards.py::test_edit_creates_new_version_and_publish_switches` |
| **AC-11** | Dashboard charts display actual analytical results | ✅ Met | Every widget POSTs to `/dashboards/{id}/widgets/{widget}/data`, which builds SQL from the stored `QuerySpec` and executes it in DuckDB. `test_widget_data_executes_real_sql` asserts the SQL and the returned KPI value |
| **AC-12** | Global filters work | ✅ Met | Categorical + date-range filters declared in the spec, applied server-side with validated fields; cross-filtering from chart clicks. `test_widget_data_executes_real_sql` (date window), `test_widget_filters_are_validated` (unknown field → 422) |
| **AC-13** | User can ask natural-language questions | ✅ Met | `test_analyst.py` (11 tests) + 55-question benchmark; UI `/app/analyst` with history, suggestions, follow-ups, feedback |
| **AC-14** | SQL queries execute through a restricted engine | ✅ Met | `test_sql_safety.py` — 16 hostile statements rejected, tables/columns allowlisted, single statement, row cap injected, blocked functions; parameters bound (`test_query_builder_parameterises_filters`) |
| **AC-15** | Numerical responses are verified against results | ✅ Met | `agents/verifier.py` + `test_analyst.py::test_revenue_matches_dataset_truth` (compares to independently computed truth), `::test_region_ranking_is_complete`, `::test_decomposition_explains_the_decline`; every benchmark case asserts verification status |
| **AC-16** | User can inspect SQL provenance | ✅ Met | Every answer returns `evidence[]` with SQL/columns/row count and `query_ids[]`; `GET /queries/{id}` returns SQL + provenance (`test_provenance_is_queryable`); UI `SQLViewer` on analyst answers and widgets; `QueryLog` persists each execution |
| **AC-17** | Basic business glossary retrieval works | ✅ Met | Approval indexes the glossary document; `test_analyst.py::test_definition_route_uses_rag_without_sql`, `test_rag.py::test_document_indexing_and_retrieval`, `::test_documents_are_isolated_between_workspaces`; UI knowledge base in settings, retrieved context shown per answer |
| **AC-18** | Tenant isolation tests pass | ✅ Met | `test_api_contract.py::test_cross_tenant_isolation` (dataset, profile, dashboard, semantic, datasets list, insights list → 404), `::test_viewer_role_cannot_write`; also `test_analyst.py::test_question_validation`, `test_insights.py::test_insight_generation_is_tenant_scoped`, `test_rag.py::test_documents_are_isolated_between_workspaces`, `test_ingestion.py::test_job_cancel_and_ownership` |
| **AC-19** | Background jobs handle failures and retries | ✅ Met | Failures persist `status=failed` + error and mark the dataset failed (`test_failed_job_is_recorded_and_retryable`); `POST /jobs/{id}/retry` re-dispatches with a bounded budget (`JOB_RETRY_EXHAUSTED`), Celery task uses `max_retries`; cancel + ownership covered |
| **AC-20** | End-to-end workflow tests pass | ✅ Met (with one caveat) | `scripts/smoke_e2e.py` runs register → demo upload → profile → semantic approve → dashboard generate → 6 analyst questions → insights → tenant isolation against the real app: **All smoke checks passed**. Browser-level E2E specs exist (`apps/web/e2e/`) but could not be executed here (no browser binary) — see `docs/TESTING.md` §6 |

## Design acceptance criteria (design spec §16)

| Area | Status | Notes |
| --- | --- | --- |
| Distinctive brand | ✅ | SVG logo/favicon, Sora + Inter, gradient accent system, no stock imagery |
| Light + dark themes | ✅ | `next-themes` with system default, persisted; both palettes defined in tokens |
| Glassmorphism, used selectively | ✅ | Glass surfaces for cards/overlays; flat surfaces for dense tables, forms and critical numbers |
| No placeholders | ✅ | Every screen is wired to real endpoints; empty states explain the next action instead of showing fake data |
| Responsive | ✅ | Single-column under 1024 px, 12-column grid above; sidebar becomes a drawer; dashboard grid collapses via CSS variables |
| Data density and typography | ✅ | Tabular numerals, compact tables, consistent 11–14 px scale |

## Deliberate non-goals (documented in `docs/LIMITATIONS.md`)

- Forecasts, anomaly detection, scheduled report emails, drag-and-drop canvas editing.
- Multi-table joins (semantic `relationships` reserved).
- SSO/2FA and physical per-tenant separation.
