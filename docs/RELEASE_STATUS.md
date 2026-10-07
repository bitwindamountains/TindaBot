# Release status

Date: 7 October 2026  
Version: 0.1.0  
Decision: **locally verified release candidate, prepared for staging deployment; public launch requires external setup and acceptance.** See the [deployment handoff](DEPLOYMENT.md).

## Delivered

The repository now contains the application, pure conversation flow, persistent event intake, worker, database migrations, catalog/inventory/order services, provider adapters, operator endpoints, CLI, tests, locked dependencies, CI, Dockerfile, Render template, backup/restore tooling, and operations documentation.

The new same-origin seller workspace includes Overview, Orders, Inventory, and Automation, with light/dark themes, responsive layouts, protected reads, existing validated mutations, memory-only operator credentials, labeled sample data, and keyboard-accessible dialogs. The ivory/ink/copper design includes an optional local ShaderGradient hero and accessible native glass controls. Its compiled assets are included in the installed Python wheel; no frontend build server is required in production. See [design audit and verification](DESIGN_SYSTEM.md).

The [feature review](FEATURE_REVIEW.md) records completed workflow improvements and prioritized remaining feature gaps. Payment follow-up, stock triage and adjustment previews, and actionable automation diagnostics are included in this revision.

The original [production review](PRODUCTION_PLAN.md) remains the design baseline. Its statement that no code exists describes the earlier review, not the current workspace.

Key scope decisions made during implementation:

- PostgreSQL acts as both system of record and durable job store. The production template uses one API and one worker; multi-worker outbound delivery remains unqualified.
- Seller status changes use a dedicated Commands tab with immutable command IDs and expected order versions. This replaces editable status cells/Apps Script callbacks and makes retries auditable.
- Shipping, pickup details, and payment methods/instructions are deploy-time configuration in this release. A seller-editable Settings tab is deferred.
- FAQ matching uses deterministic whole words/phrases. Fuzzy matching is deferred to avoid short-keyword false positives.
- Unknown Page-send echoes conservatively pause automation. Actual Page echo semantics must be tested before launch.
- Payment-proof upload and proactive order-status messages remain deferred. Status import and customer-requested tracking are implemented.

## Validation evidence

- Python 3.12 local test suite includes real PostgreSQL 17 tests for concurrent first deliveries, competing purchases, repeated confirmations, row locking, queue claims, migrations, and repeated seller commands.
- Latest full run: **64 tests passed, no skips, 77% measured package coverage**, including seven PostgreSQL tests and an HTTP API/worker subprocess restart test. The added PostgreSQL case verifies correct Manila calendar-day grouping for afternoon orders. [JUnit evidence](validation/backend-tests.xml).
- Follow-up workspace API regression run on 7 October: **4 passed**, including actual order-detail timestamps and separate failed/uncertain diagnostic counts. This supplements the earlier full backend run.
- Seventeen Chromium browser workflows cover order progression, inventory, automation, CSV export, connection/error/loading states, light/dark accessibility, keyboard operation, 320/390px layouts, retained idempotency IDs on live-API retries using mock responses, chart exploration, order sorting, glass quick actions, and ambient motion controls. The refined workspace adds a status pipeline, persistent mobile navigation, responsive order rows, scoped search, and sequential order review with fulfillment progress. Additional checks exercise real WebGL drawing/pause, refresh preservation, canvas disposal, context loss, and no-download fallbacks. Automated axe checks reported no A/AA violations in the tested views; this is not a blanket accessibility certification. [Browser evidence](validation/ui-tests.json).
- Ten-minute localhost soak completed at **10 events/second: 6,000 accepted and processed events, 6,000 dry-run replies, zero HTTP errors, and 32 ms p95 acknowledgement latency**. Maximum acknowledgement was 1.75 seconds; maximum sampled inbox age was 10.84 seconds during concurrent local test activity. The queue fully drained. This establishes local durable intake behavior, not hosted or real-provider reply latency. [Raw load report](validation/local-load.json).
- Python and npm dependency audits report no known vulnerabilities in the checked dependency sets.
- Wheel and source distribution build successfully. An isolated environment installed the wheel and verified migrations, readiness, static assets, authenticated snapshots, and unauthorized access rejection without source imports or provider calls. [Installed-wheel smoke report](validation/release-smoke.json).
- Full simulated checkout produced one PHP 440.00 order after two distinct confirmation events; inventory was allocated once and provider jobs queued without external sends.
- A custom-format PostgreSQL backup restored into a separate database; catalog row count and migration version were verified. This local drill does not establish hosted RPO/RTO or off-site backup coverage.
- Provider adapter tests use HTTP mocks and fake Sheets. No live Meta, Google Sheets, or SMTP acceptance test has been performed.
- Docker is unavailable in this workspace, so the Docker image and Compose configuration have not been executed locally. CI includes a container build/readiness check. The Render Blueprint passed local validation against [Render's published JSON schema](https://render.com/schema/render.yaml.json); see [validation evidence](validation/render-blueprint.json). No resources have been provisioned.
- CI configuration is present but has not run on a remote repository. No repository was published.
- The suite currently emits a third-party Starlette TestClient deprecation notice for httpx; tests pass. Migration to its replacement test transport can follow once compatibility is verified.

Code coverage is diagnostic, not evidence that every operational gate has passed. The provider adapters still need actual account acceptance tests.

## Remaining launch gates

| Gate | Required evidence / owner |
|---|---|
| Hosting and budget | Operator/user selects existing or new Render/Supabase resources, region, paid plans, and spending ceiling. |
| Secrets and integration setup | Configure real Meta app/Page, supported Graph version, Google service account/Sheet, SMTP, independent operator/status credentials, and production TLS database URL. |
| Public Page access | Operator verifies required permissions, subscriptions, applicable App Review/Business Verification, and a permitted non-role user end-to-end test. |
| Seller operating rules | Seller approves inventory reserved for the bot, external-sale adjustments, payment verification, expiry/cancellation, takeover, and support coverage. |
| Privacy | Seller publishes actual privacy/contact/deletion information, approves retention, and verifies the request-handling process. Full identity unlinking is not provided by the personal-field erasure endpoint. |
| Backups | Configure scheduled encrypted off-site backups and independent deletion-ledger retention. Exercise restore on the selected hosted infrastructure and agree RPO/RTO. |
| Monitoring | Connect the external health checker and platform failure alerts to a real operator notification channel; test delivery and escalation. |
| Security | Verify real DB role privileges, Sheet protected ranges/sharing, secret rotation, and provider logging settings. |
| Deployment validation | Build/run the Docker image or verify native Render deployment; rehearse compatible API/worker promotion and application rollback on staging. |
| Load and pilot | Repeat the successful local 10-events/second, ten-minute probe on staging, measure actual response/export latency, then complete five business days with one supervised seller. |

The configuration doctor confirms that the external provider credentials and privacy URL are absent in this workspace. A gitignored local `.env` was prepared with independently generated operator, status, and verification tokens; their values were not displayed. Default delivery remains `dry_run`; no paid resources were created and no real customer messages or emails were sent.

## Known operational limits

- An ambiguous provider result can hold a destination lane pending operator reconciliation; this is deliberate duplicate prevention, not guaranteed external delivery.
- A worker lease cannot fence an external Sheet request that outlives the lease. The supported first deployment uses one worker and requires reconciliation after an uncertain restart; multi-worker outbound scaling needs additional qualification.
- Erasure removes personal fields and queues Sheet cleanup but retains restricted PSID/order association metadata. Complete unlinking, external-provider deletion, and post-restore ledger replay need the documented seller/operator process or a future implementation.
- The default retention and unpaid-expiry values are proposals. Startup acknowledgement is a configuration guard, not legal or commercial approval.
- The local restore exercise covered schema/catalog recovery, not a full hosted disaster simulation or production order-to-provider reconciliation.
- The workspace supports one privileged operator credential, manually refreshed data, the latest 200 orders within 7/30 days, and the first 500 products. Truncation is labeled; CSV exports the loaded filtered rows. Staff accounts, role-specific UI, older-order browsing, and browser catalog import are not included. Larger operations can use the existing APIs and seller Sheet.
- Physical mobile hardware and non-Chromium browser acceptance remain unverified. A synthetic 4x CPU mobile viewport check is recorded separately; it does not establish a sustained frame-rate guarantee.
