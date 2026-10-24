# LedgerLens final engineering audit

Audit date: 2026-10-24 (Asia/Ho_Chi_Minh)
Scope: repository source, local SQLite runtime, synthetic workbooks, package/build
checks, Docker Compose configuration, and available tests. No push, deployment,
remote integration, or destructive database operation was performed.

## Executive decision

LedgerLens is a credible **local portfolio MVP**, but it is **not ready for an
enterprise or public deployment**. There are no P0 findings. Six bounded P1
issues were remediated and regression-tested. Two enterprise P1 blockers remain:
there is no principal/RBAC/security-audit architecture, and PostgreSQL has no
verified runtime, migration discipline, or least-privilege role split.

The most important truth-in-advertising distinction is:

- Implemented: local XLSX-to-SQLite ingestion, validation, versioned
  deduplication, lineage, exact-decimal summaries, constrained reporting,
  provider-off copilot behavior, safe XLSX export, shared-key protection, and
  automated SQLite/API tests.
- Prototype/configuration only: PostgreSQL through Docker Compose and optional
  loopback Ollama intent classification.
- Missing: ERP simulator/synchronization, business reconciliation, enterprise
  identity/RBAC/audit, migrations, CI, browser E2E, and performance benchmarks.

## Verification matrix

| Check | Result | Evidence / limitation |
|---|---|---|
| Unit + API integration + security tests | **32 passed** | `.venv/bin/python -m pytest -q`; one Starlette `TestClient` deprecation warning |
| Dependency consistency | **Passed** | `.venv/bin/python -m pip check` |
| Python bytecode compilation | **Passed** | `.venv/bin/python -m compileall -q app tests` |
| Shell syntax | **Passed** | `bash -n scripts/run_local.sh` |
| Package build | **Passed** | wheel built with `pip wheel --no-deps --no-build-isolation` because the `build` module was not installed |
| Compose parse/interpolation | **Passed** | `docker compose config --quiet` with generated temporary environment values |
| PostgreSQL runtime/migrations | **Not verified** | Docker daemon was unavailable and `postgres:16-alpine` was not present; no Alembic configuration exists |
| Ruff / mypy | **Not run** | neither tool nor project configuration exists |
| Browser E2E / visual inspection | **Not verified** | no browser automation CLI, browser surface, or browser test dependency was available |
| HTTP smoke test | **Passed** | isolated loopback server: public health 200, missing key 401, valid key 200 |
| Performance/throughput/memory | **Not measured** | no benchmark harness or README performance claim exists |

The README demo totals were reproduced by the tests: 12 accepted rows, 1
rejected row, 1 duplicate on the two first imports, revenue VND 40,800,000,
expense VND 9,640,000, receivables VND 10,800,000, and net VND 31,160,000.
These are synthetic fixture results, not user or business outcomes.

## Findings

### P0 — critical blockers

No P0 issue was confirmed. The copilot has no raw SQL or financial mutation
capability, uploads do not execute macros, and no remote deployment was made.

### P1 — security or financial-correctness issues

#### LL-P1-01 — request bodies could be parsed before authentication — fixed

- Affected: `app/main.py`, `tests/test_api.py`, `tests/test_security.py`.
- Reproduction/evidence: send malformed multipart data without `X-API-Key` to
  `/api/imports`; the baseline returned a multipart parse response before the
  route dependency. This allowed unauthenticated request buffering. A first
  remediation also gave `/api/imports/` the 8 KiB JSON allowance and rejected a
  legitimate redirecting upload.
- Fix: a pure ASGI gate now authenticates `/api` requests before reading their
  bodies, enforces 8 KiB JSON and 9 MiB multipart-envelope limits using both
  `Content-Length` and actual chunks, keeps the route guard, and canonicalizes a
  trailing slash for the upload allowance.
- Regression evidence: tests prove an unauthorized body is never read,
  malformed unauthenticated multipart returns 401, oversized JSON returns 413,
  and a multipart body larger than 8 KiB succeeds through `/api/imports/`.

#### LL-P1-02 — XLSX logical dimensions and lazy XML errors allowed excessive work/500s — fixed

- Affected: `app/etl.py`, `app/main.py`, `tests/test_security.py`.
- Reproduction/evidence: craft a valid XLSX with an actual cell at row 1,048,576,
  data only after column 60, or a worksheet XML document truncated after package
  metadata. OpenPyXL read-only iteration trusted logical dimensions, ignored
  work outside the returned 60 columns, and could raise a lazy parse exception
  after `load_workbook`, producing a 500.
- Fix: archive/member caps remain; worksheet parts are resolved through the root
  office-document and workbook relationship graph, cross-checked against package
  content types, and preflight-parsed with aggregate row/cell/nonempty-row
  budgets (including work outside the 60 schema columns). Worksheet dimensions
  are reset, application iteration is bounded, package/lazy parser failures
  become structured `ValueError`, and the synchronous import runs in FastAPI's
  worker pool rather than blocking the event loop. Harmless ancillary columns
  remain compatible.
- Regression evidence: sparse-last-row, alternate worksheet-part path,
  column-61 ancillary data, malformed-XML 422, row cap, ZIP, and ordinary
  multi-sheet fixtures pass.

#### LL-P1-03 — permitted amounts could lose cents — fixed for new local writes

- Affected: `app/database.py`, `app/reports.py`, `app/main.py`,
  `tests/test_api.py`, `tests/test_security.py`.
- Reproduction/evidence: import `99999999999998.99` into default SQLite; binary
  floating-point conversion could return a neighboring cent, while earlier JSON
  and export code also used float unconditionally.
- Fix: PostgreSQL retains `NUMERIC(18,2)`; SQLite writes exact cents as prefixed
  text through an SQLAlchemy type adapter, all aggregation uses `Decimal`, JSON
  money is a two-decimal string, and Excel uses a numeric cell only when its
  float round-trips to the exact cents (otherwise an exact string).
- Regression evidence: the large-cent value survives import, records, summary,
  export, and an idempotent reimport. Historical SQLite values already rounded
  before this fix cannot be reconstructed automatically.

#### LL-P1-04 — duplicate identity suppressed distinct transactions — fixed

- Affected: `app/etl.py`, `README.md`, `docs/INTERVIEW_DEMO_VI.md`,
  `tests/test_api.py`.
- Reproduction/evidence: at baseline, equal document/date/department/type/amount
  values with different counterparties collided. The first fix used an ASCII
  header normalizer, so `客户甲` and `客户乙` still collapsed to the same identity.
- Fix: the versioned identity now includes counterparty and preserves Unicode,
  punctuation, case-folding, and normalized spacing. Existing pre-v2 hashes are
  recognized for non-destructive local compatibility.
- Regression evidence: Chinese counterparties and `ACME-A` / `ACME A` remain
  distinct on first import and all become duplicates on exact reimport.
- Residual design constraint: the business key is still a demo assumption and
  must be confirmed per ERP/accounting domain.

#### LL-P1-05 — copilot returned plausible but unsupported global answers — fixed fail-closed boundary

- Affected: `app/agent.py`, `app/main.py`, `tests/test_api.py`.
- Reproduction/evidence: `Who is the CEO?`, weather/report wording, prompt
  override variants, `Revenue in October 2026`, `Revenue for Sales`, and
  `Revenue where status is paid` could return all-record financial totals with
  HTTP 200. No SQL or mutation occurred, but the answers were semantically false.
- Fix: a small accepted financial-report vocabulary, dangerous-token rejection,
  format-character removal, and conservative period/department/status selector
  detection run before either planner. Unsupported requests return 422.
  Successful responses explicitly identify accepted-record scope and null filters.
- Regression evidence: valid grouped questions work in provider-off mode;
  unrelated, injected, and unimplemented-filter cases fail closed.
- Residual limitation: this remains a small intent router, not the tool-registry
  agent proposed in the original roadmap. Natural-language coverage is not
  benchmarked.

#### LL-P1-06 — local launcher disclosed a reusable API key — fixed in code; restart required

- Affected: `scripts/run_local.sh`, `README.md`, local `.env` operational state.
- Reproduction/evidence: the baseline launcher printed the shared key on every
  startup. The repository has no Git metadata, so past tracking/history could
  not be checked.
- Fix: first-run generation still uses a random key and mode `0600`, but stdout
  now gives editor-based retrieval instructions and never prints the value. The
  local `.env` was rotated after validation without displaying the replacement.
- Required operator step: restart any already-running LedgerLens process; an
  existing process retains its old environment until restart. Rotate again
  before any public/demo sharing if the key has appeared in other logs or chat.

#### LL-P1-07 — PostgreSQL lifecycle and least privilege are unverified — open enterprise blocker

- Affected: `app/database.py`, `compose.yml`, repository root (missing migrations).
- Reproduction/evidence: startup calls `Base.metadata.create_all`; there is no
  Alembic directory/version table. Compose gives the application the same role
  that bootstraps the database. Only Compose configuration parsing succeeded;
  the Docker daemon was unavailable, so PostgreSQL transactions, Numeric
  behavior, constraints, and startup were not executed.
- Proposed fix: add a non-destructive Alembic baseline/revisions, separate
  owner/migrator/runtime roles, grant the runtime only required DML, back up and
  rehearse upgrades, then add disposable-PostgreSQL integration tests in CI.
- Why not changed here: inventing a migration baseline against an uninspected
  production schema or claiming runtime compatibility without a runnable server
  would be unsafe.

#### LL-P1-08 — shared-key auth cannot provide authorization or attributable audit — open enterprise blocker

- Affected: `app/main.py`, `app/database.py`, all protected routes; missing audit
  and principal models.
- Reproduction/evidence: one shared key grants all reads, imports and exports.
  Import lineage records file/row provenance, but there are no actors, roles,
  tenant/data scopes, immutable security events, rate limits, or report-execution
  history. Therefore “who viewed/exported/changed what” cannot be answered.
- Proposed fix: introduce a real principal/role/data-scope model, read/import/
  export permissions, durable audit events with request IDs and retention,
  secret-manager integration, proxy-aware rate limiting, and authorization tests.
- Why not changed here: the repository contains no identity provider, tenancy
  boundary, retention policy, or authorization requirements from which a safe
  enterprise design can be inferred. The current UI and docs explicitly retain
  local single-workspace scope.

### P2 — maintainability, feature-completeness, and usability

#### LL-P2-01 — ERP synchronization does not exist

- Affected: no ERP service, adapter, endpoint, model, UI, or tests exist.
- Reproduction/evidence: search for customers, invoices, payments, sync state,
  retry/idempotency keys, or ERP routes returns no implementation.
- Proposed fix: build an explicitly labeled simulator plus authenticated
  read-only adapter, cursor/change tracking, idempotency keys, bounded retries,
  dead-letter/failure reporting, reconciliation records, and outage tests.

#### LL-P2-02 — ingestion is safe but narrower than the requested enterprise pipeline

- Affected: `app/etl.py`, `app/database.py`, import UI.
- Evidence: merged data cells are not propagated; the uncertain row is correctly
  rejected rather than guessed. `$`/`USD` forms are rejected, and there is no
  currency column/conversion policy. Schema recognition is alias-based with no
  mapping/review UI. Browser multi-file upload is a sequential client loop, not
  a server-side atomic batch/job. There is no separate “needs review” state.
- Proposed fix: add explicit mapping templates, currency + FX policy, verified
  merged-cell rules, a review queue, background/batch state, and domain-specific
  transformation records. Keep uncertain values rejected until rules are owned.

#### LL-P2-03 — “reconciliation” is arithmetic, not source/ledger/ERP reconciliation

- Affected: `app/reports.py`, tests and UI wording.
- Evidence: revenue minus expense and separate receivable/payable totals reconcile
  to stored accepted rows, but there is no second system, expected balance,
  matching rule, mismatch record, tolerance, or reconciliation sheet.
- Proposed fix: define source-of-truth pairs and keys, store matched/unmatched/
  variance outcomes, expose drill-down, and add exact source-to-target tests.

#### LL-P2-04 — export is formatted and safe but not the full professional workbook

- Affected: `app/reports.py`.
- Evidence: generated files have Read Me, Summary, Normalized Data and Data
  Quality sheets; freeze panes, filters, number formats, conditional formatting,
  a chart, and safe string cells work. They contain no formulas, native Excel
  tables/PivotTables, data validation, reconciliation sheet, department-specific
  report, or receivables aging. Exact large cents are strings because XLSX
  numeric cells use binary floating point.
- Proposed fix: add explicit tables and missing domain sheets once reconciliation
  and aging semantics exist; state clearly when values are text for exactness.

#### LL-P2-05 — workload scales in memory and has no durable job/quota model

- Affected: `app/etl.py`, `app/reports.py`, `app/main.py`.
- Evidence: a file is buffered, parsed into `list(extract(...))`, existing
  fingerprints are loaded, all filtered rows are materialized, and workbooks are
  built in memory. Per-request caps exist, but repeated authenticated imports can
  grow the database and reporting workload without quota/rate limit.
- Proposed fix: staged imports, batched inserts, indexed server-side aggregates,
  queued exports, workspace quotas, cancellation/timeouts, and measured load
  tests before publishing scale claims.

#### LL-P2-06 — UI controls have backends, but release-grade UX is incomplete

- Affected: `app/static/index.html`, `app/static/app.js`, `app/static/app.css`.
- Evidence: key connect, grouping, upload/drop, prompt presets, ask, both exports,
  navigation and lineage table all have handlers and backend routes; request
  failures surface in a modal, status area, or toast. Source review found no
  visible fake ERP/reconciliation action. Missing items include progress,
  disabled/loading states, cancellation, batch details, issue drill-down,
  search/filter/pagination, dark mode, and robust modal focus trapping.
- Proposed fix: add stateful interaction tests and accessibility review before
  expanding navigation. This audit did not claim visual verification.

#### LL-P2-07 — automated assurance is SQLite/API-centric

- Affected: `pyproject.toml`, tests, missing CI/browser/type/lint configuration.
- Evidence: 32 local tests pass, but there are no PostgreSQL, live Ollama, ERP,
  browser E2E, concurrency, migration, load, lint, or static-type jobs. There is
  no CI workflow.
- Proposed fix: pin a CI matrix, add Ruff and mypy intentionally, run disposable
  PostgreSQL migrations/integration tests, add browser tests for every visible
  action, and publish benchmarks only from a checked-in harness/artifact.

### P3 — optional improvements

#### LL-P3-01 — external font request affects offline/privacy behavior

- Affected: `app/static/app.css`.
- Evidence: CSS imports Google Fonts; the app otherwise runs locally.
- Proposed fix: self-host licensed fonts or use the system stack exclusively.

#### LL-P3-02 — test harness emits a deprecation warning

- Affected: test dependency stack.
- Evidence: all test runs warn that Starlette's current `httpx` TestClient path is
  deprecated and suggests `httpx2`.
- Proposed fix: evaluate the supported FastAPI/Starlette test-client migration in
  a separate dependency change; do not suppress the warning without validation.

#### LL-P3-03 — generated/package artifacts can become stale

- Affected: local `build/`, egg-info, bytecode/cache artifacts if retained.
- Evidence: source tests and Docker use `app/`, not a generated `build/lib/app`
  mirror. Hand-editing generated copies would create misleading review results.
- Proposed fix: keep generated artifacts ignored/cleaned by packaging workflows
  and audit only source-of-truth paths.

## Requirement-by-requirement conclusion

1. Visible actions have source-backed handlers/routes and error surfacing; no
   browser visual/E2E claim is made.
2. Malformed archives, bad rows/dates, VND formats, duplicate identities,
   header aliases, multi-sheet files and traversal limits are covered. Merged
   recovery and multi-currency are not implemented.
3. Accepted rows retain batch/file/sheet/row lineage and exact totals reconcile
   to the stored accepted dataset. Business/ERP reconciliation is absent.
4. The copilot selects a Pydantic enum and calls allowlisted application code;
   it has no arbitrary SQL or mutation path. Enterprise authorization is absent.
5. Provider-off mode is the tested default. Unsupported/filter-specific requests
   now fail with 422 instead of receiving fabricated scoped results.
6. Model definitions are PostgreSQL-compatible by inspection and schema creation
   is non-destructive, but PostgreSQL runtime and migrations are not verified.
7. ERP sync, deduplication, retries and failure reporting are absent.
8. XLSX values/lineage/formatting/chart/filters and formula-injection defense are
   tested; formulas/native tables and several requested sheets are absent.
9. Upload hardening and local secret handling improved; enterprise auth, rate
   limits, least privilege and attributable audit remain blockers.
10. README fixture totals are supported. No performance metric is claimed or
    supported. Final local tests are reported exactly; unavailable checks remain
    labeled unavailable.

## Recruiter-facing project summary

LedgerLens is a local FastAPI portfolio MVP that ingests heterogeneous bilingual
Excel transaction workbooks, validates and deduplicates rows, preserves source
lineage in SQLAlchemy storage, serves exact-decimal financial summaries, and
exports formatted multi-sheet XLSX reports. Its natural-language layer is a
constrained report-intent classifier—deterministic by default, optionally backed
by loopback Ollama—and cannot generate SQL or mutate financial records.

PostgreSQL is configuration-level and not runtime-verified in this audit. The
project does not implement an ERP simulator, production integration, enterprise
IAM/RBAC/audit, migrations, browser E2E, or performance benchmarks.

### Resume bullets

- Built a local FastAPI/SQLAlchemy pipeline that normalizes bilingual,
  multi-sheet XLSX transaction data, validates malformed rows, preserves
  file/sheet/row lineage, and performs idempotent versioned deduplication.
- Implemented exact-Decimal financial summaries and safe multi-sheet Excel
  exports with grouped reporting, quality logs, filters, formatting, charts, and
  spreadsheet-formula injection protection.
- Designed a Pydantic-constrained natural-language report planner with a fully
  deterministic provider-off path and optional loopback Ollama classification;
  unsupported filters and prompt-injection variants fail closed, with no raw SQL
  or data-mutation capability.
- Hardened the local MVP with pre-parse API-key enforcement, bounded request and
  XLSX traversal, ZIP/member limits, Unicode-safe duplicate identity, and 32
  passing local automated tests; PostgreSQL/ERP/enterprise IAM remain future work.
