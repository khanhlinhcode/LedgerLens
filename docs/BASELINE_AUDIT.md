# LedgerLens baseline audit

Captured on 2026-10-24 before the bounded P0/P1 remediation in this audit.
This is a source-and-local-runtime baseline, not a production certification.

## Repository and runtime

- The directory was not a Git worktree, so branch, diff, history, and tracked-secret status could not be verified. Existing files and the SQLite database were preserved.
- Runtime: Python 3.12.10; FastAPI 0.162.0; SQLAlchemy 2.1.6; pandas 2.3.3; OpenPyXL 3.1.5; XlsxWriter 3.3.0; HTTPX 0.28.1; Pydantic 2.14.1.
- Persistence defaulted to local SQLite. Docker Compose described PostgreSQL 16, but the Docker daemon was unavailable, so PostgreSQL execution was not verified.
- Authentication was one shared `APP_API_KEY`. `.env` was ignored by `.gitignore` and mode `0600`, but the launcher printed the reusable key on every start.
- There was no Alembic migration history, ERP simulator, RBAC/principal model, security audit-event model, CI configuration, browser E2E suite, or benchmark harness.

## Baseline execution

| Check | Baseline result |
|---|---|
| `pytest -q` | 18 passed; one Starlette `TestClient` deprecation warning |
| `pip check` | Passed |
| `python -m compileall app tests` | Passed |
| Python package wheel | Built with `pip wheel --no-deps --no-build-isolation` |
| `docker compose config --quiet` | Passed |
| Docker/PostgreSQL runtime | Not run: daemon unavailable and image absent |
| Ruff / mypy | Not configured or installed; not run |
| Browser E2E / visual check | Not run: no browser surface or browser test dependency was available |

The local service was also started on a separate loopback port. `/healthz`
returned 200, a protected request without a key returned 401, and the same
request with the configured key returned 200. This was a smoke test, not a
visual verification.

## Baseline feature classification

| Area | Classification | Evidence at baseline |
|---|---|---|
| XLSX multi-sheet ingestion | Partial | Header aliases, date/VND normalization, row/sheet/archive limits and issue sampling existed; merged cells and non-VND currencies were unsupported. |
| Duplicate handling | Partial | Cross-batch fingerprinting existed, but counterparty was omitted and distinct transactions could collide. |
| Lineage | Implemented in storage, partial in UI/export | Batch, sheet and source row were stored; the records API/UI did not expose all lineage. |
| Financial summaries | Partial | Correct for demo values, but JSON/export paths converted Decimal to float and lost cents at large permitted values. |
| AI copilot | Partial | Enum-constrained intent selection and provider-off mode existed with no arbitrary SQL; unsupported filters/questions could silently receive global financial answers. |
| Excel export | Partial | Four sheets, formatting, filters, chart and formula-injection defense existed; no native tables, formulas, reconciliation or aging sheet. |
| Authentication/security | Partial | Shared-key guard, loopback launcher, ZIP limits and safe workbook modes existed; body parsing occurred before auth and the launcher disclosed the key. |
| PostgreSQL | Prototype/config only | SQLAlchemy URL and Compose service existed; no runtime evidence or migrations. |
| ERP synchronization | Missing | No simulator, adapter, sync state, retry, deduplication or failure-reporting code. |
| Automated verification | Partial | Unit/API integration tests existed; no browser E2E, PostgreSQL integration, performance, type-check or lint configuration. |

## Reproducible baseline defects

- Two otherwise identical rows with different counterparties produced the same fingerprint.
- A permitted amount of `99999999999999.99` became `99999999999999.98` on a float-backed reporting path.
- A request for October/Sales data returned the all-record total with HTTP 200.
- An unrelated question and a prompt-injection string returned the default financial overview with HTTP 200.
- Malformed unauthenticated multipart data was parsed before the route dependency rejected it.
- A worksheet with a far-away sparse cell caused work unrelated to the 5,000 nonempty-row limit.
- A merged department cell was not expanded: the uncertain second row was rejected and logged rather than guessed.
- `$1,000` and `USD 1,000` were rejected; the canonical model had no currency field or conversion policy.

The detailed disposition, remediations, residual risks, and final regression
results are in `docs/FINAL_ENGINEERING_AUDIT.md`.
