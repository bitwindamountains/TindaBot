# Release status

Date: 8 October 2026<br>
Version: 0.1.0  
Decision: **locally verified release candidate, prepared for staging deployment; public launch requires external setup and acceptance.** See the [deployment handoff](DEPLOYMENT.md).

## Delivered

The repository now contains the application, pure conversation flow, persistent event intake, worker, database migrations, catalog/inventory/order services, provider adapters, operator endpoints, CLI, tests, locked dependencies, CI, Dockerfile, Render template, backup/restore tooling, and operations documentation.

The new same-origin seller workspace includes Overview, Orders, Inventory, and Automation, with light/dark themes, responsive layouts, protected reads, existing validated mutations, memory-only operator credentials, labeled sample data, and keyboard-accessible dialogs. The ivory/ink/copper design includes an optional local ShaderGradient hero and accessible native glass controls. Its compiled assets are included in the installed Python wheel; no frontend build server is required in production. See [design audit and verification](DESIGN_SYSTEM.md).

The [feature review](FEATURE_REVIEW.md) records completed workflow improvements and prioritized remaining feature gaps. Payment follow-up, stock triage and adjustment previews, and actionable automation diagnostics are included in this revision.

The four findings from the [checkpoint review](FOLLOW_UP_REVIEW.md) are fixed: erasure coordinates with order-linked delivery claims, unfinished orders remain discoverable across all dates with paginated search/export, catalog failures no longer block seller commands, and navigation retains working context in tab memory.

Private order notes, paged activity history and partial/full external-refund reconciliation are now included. Notes and refund references are scrubbed by erasure/retention. This release requires schema `0003`; see [journal behavior and rollout](ORDER_JOURNAL.md).

Protected delivery recovery now includes bounded, redacted inspection, explicit duplicate-risk confirmation, optimistic state checks, idempotent resolutions and operator audit records. See [delivery recovery](DELIVERY_RECOVERY.md).

A small [human handover queue](HANDOVER_QUEUE.md) is now available in Overview and Automation, with tracked waiting counts, last-contact times, a Page inbox link and explicit version-checked resume. It uses existing conversation storage and requires no new migration. Pre-existing unmarked pauses are not backfilled; individual Messenger thread linking remains unverified.

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
- Latest full run: **102 tests passed, no skips**, including sixteen PostgreSQL tests and an HTTP API/worker subprocess restart test. Coverage is 81%. The PostgreSQL cases include Manila date grouping, customer-name search and both claim/erasure interleavings, concurrent refund retries/competing commands, and private activity-table grants. [JUnit evidence](validation/handover-backend-tests.xml).
- The latest full suite includes the earlier timestamp/diagnostic regressions plus older-order visibility, filtered cursor paging, tie ordering, insertion boundaries and preservation of dashboard totals.
- Twenty-five Chromium browser workflows cover order progression, inventory, automation, complete filtered CSV export, connection/error/loading states, light/dark accessibility, keyboard operation, 320/390px layouts, retained idempotency IDs on live-API retries using mock responses, chart exploration, order sorting, glass quick actions, and ambient motion controls. The handover cases verify explicit confirmation, STOP wording, stale resume handling, count updates, pagination and safe rendering. The delivery recovery cases verify pagination, acknowledgement, stable command IDs after response failures, mobile layouts and both themes. The journal cases verify private notes, partial-to-full refunds, queue clearing, safe text rendering and retained command IDs after a failed response. They also verify Back/Forward context and privacy, connected pagination, server search, and restoration of loaded pages. Additional checks exercise real WebGL drawing/pause, refresh preservation, canvas disposal, context loss, and no-download fallbacks. Automated axe checks reported no A/AA violations in the tested views; this is not a blanket accessibility certification. [Browser evidence](validation/ui-tests.json).
- Ten-minute localhost soak completed at **10 events/second: 6,000 accepted and processed events, 6,000 dry-run replies, zero HTTP errors, and 32 ms p95 acknowledgement latency**. Maximum acknowledgement was 1.75 seconds; maximum sampled inbox age was 10.84 seconds during concurrent local test activity. The queue fully drained. This establishes local durable intake behavior, not hosted or real-provider reply latency. [Raw load report](validation/local-load.json).
- Python and npm dependency audits report no known vulnerabilities in the checked dependency sets.
- Wheel and source distribution build successfully. An isolated environment installed the wheel and verified migration `0003`, readiness, static assets, authenticated snapshots, private notes/refund history and unauthorized access rejection without source imports or provider calls. [Installed-wheel smoke report](validation/release-smoke.json).
- Full simulated checkout produced one PHP 440.00 order after two distinct confirmation events; inventory was allocated once and provider jobs queued without external sends.
- A custom-format PostgreSQL backup restored into a separate database; catalog row count and migration version were verified. This local drill does not establish hosted RPO/RTO or off-site backup coverage.
- Provider adapter tests use HTTP mocks and fake Sheets. No live Meta, Google Sheets, or SMTP acceptance test has been performed.
- Docker is unavailable in this workspace, so the Docker image and Compose configuration have not been executed locally. CI includes a container build/readiness check. The Render Blueprint passed local validation against [Render's published JSON schema](https://render.com/schema/render.yaml.json); see [validation evidence](validation/render-blueprint.json). No resources have been provisioned.
- CI configuration is present but has not run on a remote repository. No repository was published.
- The suite currently emits a third-party Starlette TestClient deprecation notice for httpx; tests pass. Migration to its replacement test transport can follow once compatibility is verified.

Code coverage is diagnostic, not evidence that every operational gate has passed. The provider adapters still need actual account acceptance tests.

Latest browser run: all 21 workflows passed, including the real software-WebGL test with its four-minute overall allowance. The journal workflows were checked again after the final typography adjustment. The initial concurrent backend run had PostgreSQL timeouts during software rendering; the isolated full backend rerun passed all 92 cases with no skips. These local checks are not a hosted or physical-device performance guarantee.

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
- The workspace supports one privileged operator credential and manually refreshed snapshots. Orders supports all dates, actionable queues and 7/30-day reporting scopes with server filters and 200-record cursor pages; connected CSV exports fetch the complete selected result. Paging excludes new insertions after its anchor but does not freeze updates to existing orders. The product view remains capped at 500. Staff accounts, role-specific UI, custom date ranges and browser catalog import are not included.
- Physical mobile hardware and non-Chromium browser acceptance remain unverified. A synthetic 4x CPU mobile viewport check is recorded separately; it does not establish a sustained frame-rate guarantee.
