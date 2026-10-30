# Known limitations and remaining work

This file is deliberately blunt. Everything listed here is a real constraint of the current build,
not a roadmap wish.

## Data and modelling

1. **One table per dataset.** Uploaded files are analysed as a single denormalised table. The semantic
   model has a `relationships` field, but joins across multiple uploaded tables are not implemented.
   Multi-sheet Excel selection is supported (one sheet becomes the dataset).
2. **No incremental refresh.** A dataset version is an immutable snapshot. There is no scheduled
   re-upload, no change-data-capture and no streaming.
3. **Cleaning is conservative.** Only `drop_duplicates`, `trim_whitespace` and `drop_all_null_rows`
   are applied, and only when a user opts in. Type coercion happens at ingestion; there is no manual
   type editor or expression builder.
4. **Metric expressions are constrained.** Metrics are SUM/AVG/COUNT/COUNT_DISTINCT/MIN/MAX or a ratio
   of two existing metrics. Arbitrary calculated fields are intentionally rejected to keep the SQL
   policy airtight; a windowed-expression editor is not implemented.
5. **Forecasting, anomaly detection and clustering are not implemented.** The platform reports what
   happened and why the numbers moved, not what will happen. The eval benchmark includes a forecast
   question specifically to assert a graceful refusal.
6. **Causality is not claimed.** Decomposition attributes movement to dimension contributions
   (“statistical contributions”), never to proven causes.

## AI

7. **Gemini path is unexercised in this environment.** No API key was available, so all verification
   ran in deterministic mode. The Gemini client is implemented with structured JSON validation,
   retries and a deterministic fallback, but live behaviour (latency, occasional malformed JSON,
   embedding quality) has not been observed here.
8. **Deterministic embeddings are lexical.** Without Gemini, retrieval uses a hashed bag-of-words
   embedding. It works for glossary/policy lookups but is weaker than a trained model for paraphrase
   and multilingual content.
9. **Retrieval is bounded and in-process.** Cosine similarity is computed over up to 800
   tenant-scoped chunks per query. That is fine for hundreds of documents; a corpus of tens of
   thousands needs the pgvector ANN path (implemented in migration `0002`) and benchmarking.
10. **No streaming responses.** Analyst answers arrive as a single JSON payload; there is no
    token-by-token stream, no cancellation of an in-flight LLM call.
11. **No fine-tuning or feedback loop.** Helpful/not-helpful votes are stored per message but do not
    train or re-rank anything yet.

## Infrastructure

12. **SQLite is the default.** It is single-writer and unsuitable for concurrent production traffic.
    PostgreSQL is the intended deployment target; the pgvector migration and Compose service exist,
    but the PostgreSQL path was not executed here (no server available).
13. **Celery path is configured but unexercised.** Local runs use the in-process thread worker. The
    Celery app, task and worker service are present; a real Redis-backed deployment has not been
    tested in this environment.
14. **Rate limiting is per-process and in-memory.** With multiple API replicas the effective limit is
    multiplied. Move the limiter to Redis before scaling out.
15. **No SSO/SCIM, no 2FA.** Email + password (bcrypt) with invitation records. Email delivery is not
    configured: password-reset and invitation tokens are surfaced in the API response only in
    non-production environments.
16. **Single-region, single-tenant-per-database privacy model.** Isolation is row-level by
    organisation/workspace. There is no per-tenant encryption key or physical separation.
17. **No audit export or retention policy.** Audit rows are written but there is no scheduled export,
    rotation or retention setting.

## Frontend

18. **Playwright specs ship unexecuted.** The sandbox could not download a browser
    (`cdn.playwright.dev` is unreachable) and has no system Chrome. Specs and config are included and
    documented; they are not claimed as passing.
19. **No drag-and-drop grid editing.** Dashboards can be edited (title, width, add/remove widget,
    filters) but widgets are not free-form draggable/resizable as in a canvas editor.
20. **No PDF/PNG export or scheduled email reports.** CSV export of widget rows is available in the UI
    path via the data table, but a report scheduler is not implemented.
21. **Charts are a fixed registry.** Nine widget types (KPI, line, area, bar, pie, donut, scatter,
    data table, heatmap). New chart types require a code change by design.
22. **Accessibility is partial.** Semantic landmarks, focus states and ARIA labels are present, and
    charts expose an `ariaLabel`, but there has been no formal WCAG audit or keyboard-only walkthrough.
23. **No i18n.** Copy is English-only; numbers/dates use `en-US` formatting with an INR currency symbol
    for demo data.

## Verification scope

24. **The verifier checks numbers, not meaning.** It proves a cited figure exists in the executed
    result set (or is a derivable share/delta). It cannot detect a plausible but wrong metric choice,
    e.g. “revenue” mapped to gross rather than net. That is why semantic-model approval is mandatory
    and metric definitions carry `requires_approval` semantics.
25. **Query timeout uses DuckDB `interrupt()`.** It stops the offending query and resets the cached
    connection, but a pathological query can still consume memory up to the configured limit before
    interruption.

## Test coverage gaps

26. No load/performance testing, no chaos testing, no fuzzing of the parsers beyond the hostile cases
    in `tests/test_ingestion.py`.
27. The PostgreSQL-specific branches (pgvector ordering, Alembic `ALTER … TYPE vector`) are not
    exercised by the local suite.
28. Cross-browser behaviour is untested (Chromium only, and only once a browser is available).

## Deliberate scope decisions

- **No LLM-generated UI.** Enforced structurally: the dashboard schema allowlist rejects unknown
  widget types and encodings, and the renderer only knows the registry.
- **No client-side analytics.** Every number is recomputed on the server; charts receive exact rows.
- **Deterministic-first AI.** The product must be useful and honest without an API key, so every AI
  step has a deterministic implementation rather than a placeholder.
