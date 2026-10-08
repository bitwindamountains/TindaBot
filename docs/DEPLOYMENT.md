# Deployment handoff

Prepared 4 October 2026. This is a locally verified release candidate for staging deployment. Hosting, live provider acceptance, and public launch have not been performed.

## Release contents

- Python 3.12 application, API, worker, and Alembic migrations.
- Same-origin seller workspace packaged in the Python wheel and Docker source. The ShaderGradient bundle is compiled during development/CI and shipped with the source. No CDN, external font, or Node runtime is needed on the production server.
- Locked Python, graphics, and browser-test dependencies, CI, Render Blueprint, migration/readiness checks, and backup/restore tooling.
- Default local mode is `dry_run`; the production configuration deliberately requires explicit live configuration and acknowledgement.

## Local release gate

Run from the repository root, with `TEST_DATABASE_URL` pointing only at a disposable PostgreSQL database ending in `_test`:

```text
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov=tindabot --junitxml=docs/validation/backend-tests.xml
uv run pip-audit --skip-editable
npm ci
npm run build:effects
npx playwright install --with-deps chromium
npm run test:ui
npm audit --audit-level=moderate
uv build
uv run python scripts/validate_deploy.py
```

On Windows with execution-policy restrictions use `npm.cmd` and `npx.cmd`; omit `--with-deps` on Windows. The isolated installed-wheel smoke test is `scripts/smoke_release.py`; run it with the Python interpreter of an environment containing the built wheel and locked runtime dependencies. It migrates a temporary SQLite database, exercises readiness, verifies all packaged web assets, and checks authenticated data access without calling providers.

## Hosting inputs

The existing target template is Render with a separate PostgreSQL service supplied by the operator. Before provisioning, supply the hosting account/project, approved region and plans, database connection, and production domain. Paid service creation has not been authorized against a specific account or budget.

Populate the shared `tindabot-production` environment group using `.env.example` as the inventory:

| Group | Required inputs |
| --- | --- |
| Database | `DATABASE_URL` using `postgresql+psycopg`, TLS, and a direct/session connection; supported production role privileges. |
| Meta | App/Page IDs, app secret, verify token, Page access token, and currently supported Graph API version. |
| Operator access | Independent, randomly generated `ADMIN_TOKEN` and `STATUS_TOKEN`, at least 32 characters each. Never embed them in frontend files, URLs, or repository settings. |
| Seller sheet | Sheet ID and base64 service-account JSON; restricted sharing and protected system columns. |
| Seller email | SMTP host/port/user/password/from address and seller notification address. |
| Shop and policies | Shop name, HTTPS privacy notice, pickup/delivery/payment configuration, approved retention and expiry settings. |
| Launch switches | `APP_ENV=production`, `DELIVERY_MODE=live`, `PRODUCTION_ACKNOWLEDGED=true` only after the documented operating decisions are accepted. |

Run `uv run tindabot doctor` to check the configured environment. It reports missing variable names rather than secret values. Do not share `.env` or raw provider configuration in tickets.

## Staging and promotion

1. Publish the reviewed revision to the chosen private repository and run remote CI. Record the revision and release artifact hashes. Local build output is in `dist/`.
2. Configure an isolated staging database and test provider accounts. Keep real customer traffic disconnected. For a credentials-free infrastructure smoke test use development mode with dry-run delivery; this is not production acceptance.
3. Deploy the API and run one coordinated `alembic upgrade head` pre-deploy step. Verify `/healthz`, `/readyz`, `/`, and the workspace assets over HTTPS.
4. Deploy one compatible worker. Verify `/admin/health`, queue delay, and the worker heartbeat. Keep API and worker on the same revision/configuration.
5. Open the workspace. Confirm preview labeling, connect with the operator token, then verify a permitted test checkout, order details, status conflict handling, stock adjustment, Sheet projection, seller notification, and human handover.
6. Test automation pause: queued Messenger replies are suppressed; a send already in progress may finish. Existing orders, Sheet exports, and emails continue. Resuming does not replay suppressed messages.
7. Exercise backup/restore, monitoring delivery/escalation, and application rollback on the selected infrastructure. Repeat the documented load probe on staging.
8. Promote only after provider permissions, privacy/retention approval, seller operating rules, and the supervised pilot in `RELEASE_STATUS.md` are complete.

## Workspace operating limits

- This is a single-shop operator interface, using the existing privileged bearer token. It does not provide individual staff accounts, role-specific UI, or per-person audit attribution.
- Data refreshes on request. The selected period is 7 or 30 Manila calendar days. Order value includes shipping and unpaid orders, excludes cancelled orders, and must not be read as settled revenue.
- Orders defaults to All dates and supports Needs attention or Reporting period scopes. Server-side filters and 200-record cursor pages reach older orders; connected CSV exports fetch all matching pages. Pending counts span all dates, while financial reporting remains period-based. Product browsing remains limited to the first 500 records; active-product totals include the entire catalog.
- A failed stock request can have an uncertain network outcome. Retry within the same dialog to reuse the adjustment ID. Before closing and making a new adjustment, refresh and reconcile the actual stock.
- Existing APIs and the seller Sheet remain available for larger catalogs and older records. There is no browser product-import flow, customer messaging composer, or payment processor.

## Remaining external evidence

Docker/Podman is unavailable locally, so the container is checked by the configured CI job rather than a local run. Remote CI has not run. No real Meta/Google/SMTP account acceptance, hosted migration/rollback, or physical mobile-device performance test has been completed. These are explicit release gates, not inferred successes from local tests.
