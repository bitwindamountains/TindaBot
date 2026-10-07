# Follow-up review - 7 October 2026

Reviewed checkpoint: `230fb9b` (`Save TindaBot release candidate and seller workspace`). The checkpoint was committed before review. This review changes documentation only; the findings below are not fixed.

## Findings in implementation order

### 1. P1 - Include order-linked deliveries in the erasure guard

Location: `src/tindabot/privacy.py:23-34`, with job creation in `src/tindabot/orders.py:81-82` and `src/tindabot/db.py:155-169`.

The in-flight check and suppression query match only `Outbox.conversation_key`. Checkout Sheet exports and order emails are enqueued with `order_id` and a null conversation key. Consequently, erasure accepts a request while an export for that customer's order is processing. The worker may already hold a detached copy containing the old personal fields and finish exporting it after local erasure. A later queued erasure export can clean the Sheet, but the intended in-flight refusal is bypassed and cleanup depends on that later delivery succeeding.

Isolated reproduction: seed a customer, order and processing Sheet job linked only by order ID; invoke `erase_customer`. Result: `{"orders": 1, "sheet_erasure": "queued"}`, while the original job remains `processing` with a null conversation key.

Follow-up: include jobs belonging to the customer's orders in both checks and suppression. Coordinate job claiming with erasure so a new claim cannot slip between checking and suppressing. Preserve already-delivered audit outcomes where possible.

Acceptance: order-linked Sheet and email jobs trigger the same refusal as Messenger jobs; a PostgreSQL claim/erasure race cannot export a pre-erasure snapshot after successful erasure; queued Sheet cleanup is reconciled separately from local completion.

### 2. P1 - Keep unfinished work visible independently of report dates

Location: `src/tindabot/workspace.py:41-69` and the pending brief/list in `src/tindabot/web/app.js:56,129-135`.

The reporting date predicate also restricts pending counts and the only browsable order collection. A pending COD order older than 30 days is absent from every available period, even though it still needs action and remains available through the detail API. The latest-200 cap can also hide an older pending order within the period. A truncation notice does not provide a way to reach it.

Isolated reproduction: seed one pending COD order created 31 days ago. The 30-day snapshot returns zero pending, zero loaded orders and `orders_truncated=false`; the protected detail endpoint still returns HTTP 200 with `status=pending`.

Follow-up: separate all-time actionable queues from period-based reporting. Add server-side status/payment/search filters and stable cursor pagination, then custom date ranges and exports matching the complete selected result set. Apply equivalent pagination to the 500-product catalog limit.

Acceptance: pending, unfulfilled and refund-required records remain discoverable regardless of age or position in the collection; counts correspond to reachable results; pagination remains stable during new insertions; exports clearly state their scope.

### 3. P2 - Process seller commands independently of catalog validation

Location: `src/tindabot/worker.py:248-288`.

Catalog reading/import and command processing share one exception boundary. A malformed product price, missing FAQ field or other catalog validation error exits synchronization before Commands is read. That prevents valid payment, cancellation and pause commands for existing orders from being processed until an unrelated catalog problem is repaired. Workspace/API actions remain available.

Isolated reproduction: make `read_catalog` raise a synthetic validation error and provide a valid Commands response. Neither `commands` nor `command_result` is called.

Follow-up: give catalog refresh and command processing independent error handling and health fields. Keep checkout freshness enforcement and command idempotency intact.

Acceptance: invalid catalog input preserves the last good catalog and reports its failure while valid existing-order commands still execute once and receive results. Provider-wide failures are reported without unbounded retries.

### 4. P2 - Preserve workspace navigation and filter context

Location: `src/tindabot/web/app.js:216-218,376`.

Section navigation replaces the current browser history entry and resets filters/search. Browser Back therefore cannot return from Inventory to the preceding Orders view. For a connected operator, leaving and reloading the app also clears the intentionally memory-only credential. This is a source-review finding; no new browser-history regression was run during this review.

Follow-up: create history entries for deliberate section navigation, restore section/filter/search/sort state on Back/Forward, and retain per-section context. Keep tokens and customer details out of URLs and persistent storage. Prefer semantic navigation links where practical.

Acceptance: Orders with filters -> Inventory -> Back restores the same order queue and focus; Forward works; reload/deep links initialize consistently; no credential is serialized.

## UI and feature improvements after correctness fixes

Visual assessment used the saved desktop overview screenshot in `docs/validation/workspace-refined.png`; it is not a fresh browser or physical-device verification.

- Reduce repeated pending-order information across the hero, metric strip and short list. Make the primary work panel show distinct actions: overdue confirmations, unpaid fulfillment, stock shortages and unresolved deliveries. Keep period metrics clearly separated from outstanding work.
- Offer a compact working layout with more orders above the fold while retaining the ivory, ink and copper identity. Keep ambient motion in the overview and preserve the mobile/reduced-motion fallback.
- Restore filters and scroll position after returning from an order; provide a direct next actionable order flow. Add visible snapshot age and a refresh affordance near operational counts.
- Add audited external-refund reconciliation, protected redacted job inspection, and catalog import previews using the acceptance criteria already recorded in `FEATURE_REVIEW.md`.

## Verification and launch sequence

This review ran three focused probes against a temporary SQLite database and a mocked seller adapter. They reproduced findings 1-3 without reading private configuration, touching the working shop database or contacting providers. The probes are not a PostgreSQL concurrency qualification. No production source changed and the full regression suite was not rerun.

Implement findings 1-3 first with targeted regressions, including a real PostgreSQL race test for erasure. Next implement navigation and complete queues, then the remaining seller workflows and compact layout. Run the full backend/browser checks on the resulting revision before building a new release artifact.

Public launch still requires real Meta/Sheets/SMTP acceptance, hosted deployment/container verification, working monitoring, backup/restore acceptance and the supervised seller pilot described in `RELEASE_STATUS.md`. Existing local test evidence does not close these gates.
