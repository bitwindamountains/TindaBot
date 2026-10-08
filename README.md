# TindaBot

A Messenger ordering service for one Facebook Page: product browsing, Taglish FAQs, guided checkout, order tracking, seller takeover, PostgreSQL inventory, and Google Sheets operations.

**Release status: implemented locally; not deployed or approved for public orders.** Live provider access, seller decisions, monitoring setup, and the supervised pilot are still required. See [release status](docs/RELEASE_STATUS.md) and [production plan](docs/PRODUCTION_PLAN.md).

## What is implemented

- Raw-body webhook signature checks, Page validation, bounded bodies, durable intake before acknowledgement, and duplicate-event protection.
- Pure conversation transitions; delivery/pickup, configured COD/GCash/bank instructions, Unicode names, PH phone validation, and confirmation tied to a checkout ID/version.
- Atomic order and inventory allocation, price-change reconfirmation, cancellation/restock, unpaid expiry, and customer-owned tracking.
- Separate API and worker processes; transactional outbox, independent destination retries, ordered jobs, uncertain-delivery review, and stale reply/window checks.
- Sheet catalog import, order projection using raw cell values, an explicit Commands tab for seller status changes, and seller email containing minimal customer data.
- Operator credentials distinct from status credentials, global automation switch, human takeover, privacy field erasure, retention, health checks, migrations, CI, and backup tooling.
- Responsive seller workspace at `/`: light/dark themes, order overview and detail, status changes, private order notes/history, external-refund tracking, stock adjustments, CSV export, and automation controls. The public shell shows labeled sample data until an operator connects.

No customer messages or emails are sent in the default `dry_run` mode. Dry-run jobs are recorded as `dry_run`, never as delivered. They are not automatically replayed when switching to live mode.

## Run locally

Python 3.12 is required. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) or use the existing `.venv/Scripts/uv.exe` in this Windows workspace.

```powershell
uv sync --frozen
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Fill the local test Page settings and generate independent tokens using:
uv run tindabot new-token
uv run alembic upgrade head
uv run tindabot seed-demo
uv run uvicorn tindabot.main:create_app --factory --port 8000 --no-access-log
```

In another terminal:

```powershell
uv run tindabot worker
```

`/healthz` is process liveness; `/readyz` verifies the expected database migration. Development API docs are at `/docs`. The operator health endpoint is `GET /admin/health` with `Authorization: Bearer <ADMIN_TOKEN>`.

Open **http://127.0.0.1:8000/** for the seller workspace. Preview edits stay in the browser. Choose **Connect shop** and enter your local `ADMIN_TOKEN` to use the actual database. The token stays in tab memory; reload or disconnect clears it. Status-only tokens cannot read customer data. Production connections must use the host's HTTPS URL.

Use **Ctrl/Cmd+K** for quick actions, or **/** to search. Explore daily order values by hovering the chart or using its keyboard-accessible slider. Ambient motion can be paused at the bottom of the workspace; it also respects system reduced-motion preferences and pauses offscreen or in a hidden tab.

For a complete simulated order without any provider credentials:

```powershell
uv run python scripts/demo_order.py
```

SQLite is for sequential local demonstrations. For lock/concurrency testing, start PostgreSQL using `docker compose up -d postgres` and set `DATABASE_URL=postgresql+psycopg://tindabot:local-development-only@127.0.0.1:5432/tindabot` before migrating. The Compose password is deliberately development-only, and its port binds to localhost.

## Test and build

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pip-audit --skip-editable
uv build
```

PostgreSQL tests require a **disposable database whose name ends in `_test`**:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@localhost:5432/tindabot_test'
uv run pytest -q --cov=tindabot --cov-report=term-missing
```

Those tests truncate tables and exercise migration downgrade/upgrade in the named test database. Never point them at production. CI provisions its own PostgreSQL service and runs these tests. Without the variable, PostgreSQL tests are explicitly skipped.

The isolated ShaderGradient hero build and browser checks use Node 24 during development/CI; the deployed workspace has no Node runtime dependency:

```powershell
npm.cmd ci
npm.cmd run build:effects
npx.cmd playwright install chromium
npm.cmd run test:ui
```

The generated `src/tindabot/web/effects/` bundle and license notices are included in release artifacts. Regenerate and commit them after changing `frontend/hero.jsx` or its dependencies, before `uv build`. Mobile, reduced-motion, data-saver, and unsupported WebGL clients use the lightweight CSS fallback.

Use `npm`/`npx` on Linux or macOS. The runner starts its own localhost API when needed. Screenshots and accessibility checks cover light/dark themes, mobile layouts, keyboard operation, and loading/error states. See [design audit, tokens, and motion specifications](docs/DESIGN_SYSTEM.md) and the [feature review](docs/FEATURE_REVIEW.md).

For a paced API/worker load probe, create a separate **empty** PostgreSQL database ending in `_test`, set `LOAD_DATABASE_URL`, then run:

```powershell
uv run python scripts/load_probe.py --seconds 600 --rate 10 --output docs/validation/local-load.json
```

The probe starts localhost-only processes and forces dry-run providers. Its measurements cover internal intake/processing, not real Messenger delivery or hosted infrastructure. `uv run python scripts/validate_deploy.py` independently checks the Render YAML against the provider's published schema without provisioning anything.

The first [local load report](docs/validation/local-load.json) records 6,000 events over ten minutes, zero HTTP errors, and 32 ms p95 webhook acknowledgement. Repeat on staging with the intended provider configuration before public launch.

## Connect a test Page and Sheet

1. Configure a test Meta app/Page, secret, verification token, Page token, app ID, and a currently supported Graph API version. Keep secrets in `.env` or the host secret store.
2. Expose the local API through an HTTPS development tunnel. Register `/webhook` and subscribe the Page to the messaging/postback/echo events supported by the chosen API version. Verify real payloads against the parser.
3. Create a Google service account and share only the intended spreadsheet with it. Put its base64-encoded JSON in `GOOGLE_SERVICE_ACCOUNT_JSON_B64`. Base64 is transport encoding, not encryption.
4. Run `uv run tindabot setup-sheet` to create missing tabs. It preserves existing tabs. Populate Products and FAQ, then restrict sharing and protect system columns.
5. Configure SMTP with TLS and a suitable sender account. Set `DELIVERY_MODE=live` only when the integrations are configured and you intend the application to send messages during your test.
6. Run `uv run tindabot setup-profile`, then test browsing, checkout, duplicate delivery, tracking, and seller takeover on the Page.

`setup-sheet` and `setup-profile` change external resources when explicitly invoked. Neither was run against a real account during implementation.

## Seller workflow

| Tab | Editable fields | Behavior |
|---|---|---|
| Products | `sku,name,price,stock,active,image_url` | `price` is PHP with up to two decimal places. `stock` initializes **new SKUs only**. Refreshing an existing SKU never replenishes sold stock. |
| FAQ | `keywords,answer` | Comma-separated whole words/phrases; ordered deterministic matching, no free-form AI. |
| Orders | None | Worker-owned projection, protected against manual changes. DB remains authoritative. |
| Commands | `command_id,order_id,expected_version,action` | Append a unique command ID; copy order ID/version from Orders; use `confirmed`, `paid`, `shipped`, `delivered`, `cancelled`, `pause`, or `resume`. Worker writes `result`. |

Commands are reconciled every minute. Reusing a command ID cannot apply another order transition. Incorrect versions or invalid transitions are rejected visibly. Use a **new command ID** after correcting a rejected command. Do not edit an accepted command row.

Catalog/payment settings such as shipping, pickup address, and payment instructions live in environment configuration for this release. Changing them requires redeployment; checkout reconfirms changed quotes. Inventory replenishment uses **Inventory → Adjust stock** in the authenticated workspace, or `/admin/stock` with a unique adjustment ID. Positive values add stock; negative values remove it.

Seller replies from another application or an unrecognized Page sender conservatively pause the bot. Own sends are identified by app ID and returned message ID. Verify this on the actual Page before launch. `MENU` explicitly returns the customer to the bot; there is no automatic timeout resume.

The Commands `pause`/`resume` actions identify conversations through an existing order. For pre-order inquiries, use the Page inbox reply takeover or the operator endpoint. Exact seller identity cannot be reliably inferred from an absent echo field, so unknown Page sends intentionally cause a pause.

## Deployment

The checked-in [Render Blueprint](render.yaml) describes a paid API and worker sharing an externally supplied PostgreSQL database. It does not provision a Supabase project. Configure the `tindabot-production` environment group before applying it; paid service selection and region must fit the seller's budget and data requirements.

Deploy the API first so its coordinated pre-deploy migration completes, then the compatible worker revision. Production startup rejects SQLite, missing live integration settings, weak/equal admin credentials, absent HTTPS privacy URL, and an unacknowledged production configuration. Disable public API docs and access logging; keep webhook URLs and bearer tokens out of logs.

Use a direct or session-pooled database connection with `sslmode=require` or stronger validation. The runtime currently uses normal psycopg prepared statements; **transaction-pooler URLs are not supported by this release configuration**. The database application role needs access only to these tables and sequences. Migrations revoke table/sequence access from Supabase's `anon` and `authenticated` roles when those roles exist.

Render supports a pre-deploy migration step on paid services; Supabase distinguishes session and transaction pooling. [Render deploy lifecycle](https://render.com/docs/deploys), [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres).

Shared-group secrets must be entered manually before deployment: Render ignores `sync: false` variables inside environment groups. The Blueprint therefore declares only non-secret shared defaults and preserves separately configured secrets. [Render Blueprint environment groups](https://render.com/docs/blueprint-spec#environment-groups).

Follow the [deployment handoff](docs/DEPLOYMENT.md), [operations runbook](docs/OPERATIONS.md), and [launch checklist](docs/RELEASE_STATUS.md) before routing public orders.

## Important operational limits

- PostgreSQL ensures one committed order per checkout. External messaging, email, and Sheet writes cannot share that transaction. Ambiguous Messenger/SMTP results require operator reconciliation; automatically retrying them could duplicate a notification.
- Sheets have no uniqueness constraint or transactional editing contract. Exports are serialized and reconcile by order ID; duplicate rows stop delivery for review. A single production worker is the supported initial deployment. A Sheets operation extending beyond its lease requires reconciliation; multi-worker outbound scaling is not yet release-qualified.
- A reply already in flight when a seller pauses cannot be recalled. New replies are checked immediately before dispatch.
- Personal-field erasure removes controlled name/phone/address/message copies and queues Sheet cleanup. Restricted PSID/order association metadata remains for accounting and suppression. This is not complete identity unlinking or deletion from Meta, seller email, or historical backups.
- Payment screenshots, proactive status messages, full identity unlinking, multi-Page service, AI answers, and courier integrations are not implemented.
