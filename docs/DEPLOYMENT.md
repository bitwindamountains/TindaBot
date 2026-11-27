# Deployment handoff

Reviewed 8 October 2026. This is a locally verified release candidate for staging deployment. Hosting, live provider acceptance, and public launch have not been performed. See the [deployment readiness review](dev-notes/reviews/DEPLOYMENT_REVIEW.md) for current evidence and release blockers.

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

1. Push the reviewed revision to the existing repository and require successful CI for that exact commit. [CI run 39211902992](https://github.com/bitwindamountains/TindaBot/actions/runs/39211902992) passed on `5949d71`; any later commit needs its own successful run. Record the revision and release artifact hashes. Local build output is in `dist/`.
2. Configure an isolated staging database and test provider accounts. Keep real customer traffic disconnected. For a credentials-free infrastructure smoke test use development mode with dry-run delivery; this is not production acceptance.
3. Deploy the API and run one coordinated `alembic upgrade head` pre-deploy step. Verify `/healthz`, `/readyz`, `/`, and the workspace assets over HTTPS.
4. Deploy one compatible worker. Verify `/admin/health`, queue delay, and the worker heartbeat. Keep API and worker on the same revision/configuration. The worker waits without updating its heartbeat or processing jobs until the database reports the required schema, then resumes automatically.
5. Open the workspace. Confirm preview labeling, connect with the operator token, then verify a permitted test checkout, order details, status conflict handling, stock adjustment, Sheet projection, seller notification, and human handover.
6. Test automation pause: queued Messenger replies are suppressed; a send already in progress may finish. Existing orders, Sheet exports, and emails continue. Resuming does not replay suppressed messages.
7. Exercise backup/restore, monitoring delivery/escalation, and application rollback on the selected infrastructure. Repeat the documented load probe on staging.
8. Promote only after provider permissions, privacy/retention approval, seller operating rules, and the supervised pilot in `RELEASE_STATUS.md` are complete.

## Public demo

`render.demo.yaml` deploys a single free web service for showing TindaBot to prospects. It runs with `DEMO_MODE=true`, `DELIVERY_MODE=dry_run` and SQLite on the instance's ephemeral disk, migrated and seeded with the sample shop (`tindabot seed-demo` seeds the same six products as the browser preview) on every start.

- Visitors see the sample workspace and can use **Talk to your bot** without a token through the public, read-only `POST /demo/test-chat`. It shares the operator test chat's code, so nothing is saved or sent.
- No secrets are set, so operator endpoints return 401, the webhook returns 403, and `/docs` is hidden. Settings refuse `DEMO_MODE` with `APP_ENV=production` or live delivery.
- There is no worker, Messenger, Sheet or email. Never add provider credentials or a real `DATABASE_URL` to the demo service.
- The public chat allows 30 messages a minute per visitor and 300 a minute overall, then returns 429 with `Retry-After` (`DEMO_CHAT_PER_VISITOR` and `DEMO_CHAT_OVERALL` in `workspace.py`). The visitor key is the first `X-Forwarded-For` address, which a client can forge, so the overall cap is what bounds load. Counters are in memory per process.

Deploy: Render → New → Blueprint → choose `render.demo.yaml`. Check `/readyz` and `/demo` (`{"enabled": true}`), then open `/#automation`.

## Workspace operating limits

- This is a single-shop operator interface, using the existing privileged bearer token. It does not provide individual staff accounts, role-specific UI, or per-person audit attribution.
- Data refreshes on request. The selected period is 7 or 30 Manila calendar days. Order value includes shipping and unpaid orders, excludes cancelled orders, and must not be read as settled revenue.
- Orders defaults to All dates and supports Needs attention or Reporting period scopes. Server-side filters and 200-record cursor pages reach older orders; connected CSV exports fetch all matching pages. Pending counts span all dates, while financial reporting remains period-based. Product browsing remains limited to the first 500 records; active-product totals include the entire catalog.
- Private notes, activity history and external refund reconciliation require migration `0003`. Promote matching API/worker builds and use a `0003`-compatible rollback target; older builds that require exactly `0002` fail readiness. Keep the refund ledger in backups and do not downgrade away recorded refunds. See [rollout details](ORDER_JOURNAL.md).
- A failed stock request can have an uncertain network outcome. Retry within the same dialog to reuse the adjustment ID. Before closing and making a new adjustment, refresh and reconcile the actual stock.
- Existing APIs and the seller Sheet remain available for larger catalogs and older records. There is no browser product-import flow, customer messaging composer, or payment processor.
- Customer order updates are off until the seller switches each one on in Automation. They are sent only within Messenger's 24-hour window and pause with automated replies. The test chat needs the operator token and a catalog synced within the last hour; it never writes or sends.

## Remaining external evidence

Docker/Podman is unavailable locally. [Remote CI on `334152c`](https://github.com/bitwindamountains/TindaBot/actions/runs/37754352899) passed, including its container build and API readiness check. The current revision still requires its own CI run, including the new worker heartbeat check and Python 3.12.15 runtime. No real Meta/Google/SMTP account acceptance, hosted migration/rollback, or physical mobile-device performance test has been completed.

Render now requests Python 3.12.15, a [Python security release](https://www.python.org/downloads/release/python-31215/). CI obtains it through `actions/setup-python`; the pinned uv version's bundled download catalog stops at 3.12.14. Local Windows tests still use 3.12.10. Verify the target runtime and full CI before promotion; passing dependency audits alone does not validate the interpreter or base image.
