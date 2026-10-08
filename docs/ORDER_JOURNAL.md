# Order notes, history and external refunds

Implemented 8 October 2026. Requires database migration `0003` and matching API/worker code.

## Seller workflow

Open an order to see **Activity & notes**. Add packing instructions or follow-up details as a private note of up to 2,000 characters. Notes are appended to the history, not sent to the customer or copied into the seller Sheet. Correct an earlier note by adding a follow-up; editing/deleting history is not offered.

The timeline records new order creation, payment/fulfillment changes, notes, external refund records, and personal-field removal. Entries show Manila time and the source: Customer, Operator, Seller sheet or System. Operator identifies the shared privileged role, not an individually authenticated staff member. Older orders do not gain invented historical events. The newest 50 entries load first; Load earlier activity reaches older entries.

For a paid order that was cancelled, **Refund tracking** shows the recorded and remaining amounts. Choose **Record external refund** only after returning money outside TindaBot. Enter the PHP amount, a transfer/receipt reference, and optionally the completion time in your device time zone. A blank time records the server's current time. Confirm that the money has already been sent, then save.

Partial refunds keep the order marked **Refund required**. When recorded refunds equal the full order total, payment status becomes **Refunded** and the cancelled order leaves Needs attention. The Refunded payment filter finds completed records. This does not initiate payments, verify provider receipts or change released stock.

Refund entries are append-only. There is no automatic reversal or editable balance. Verify amount/reference before saving; an incorrectly recorded refund requires operator investigation rather than another compensating payment or a blind database edit.

## API and consistency

- `POST /admin/orders/{order_id}/notes`: `command_id`, `expected_version`, `body`.
- `POST /admin/orders/{order_id}/refunds`: `command_id`, `expected_version`, positive integer `amount_minor`, `reference`, optional Unix-seconds `completed_at`.
- `GET /admin/workspace/orders/{order_id}` includes `activity`, `next_activity_cursor`, `refunded_minor` and `anonymized`.
- `GET /admin/workspace/orders/{order_id}/activity?before=ID` returns the next bounded history page.

All require the operator token. The status-only credential cannot read or write notes/refunds. Notes and references are rendered as text. Responses containing journal data use `Cache-Control: no-store`.

The order lock and version check serialize changes; idempotent retries reuse the same command ID and payload. A successful retry returns the original result and does not add another ledger entry. Reusing a command for changed content is rejected. Notes and refund entries advance the order version and queue a Sheet export of the usual order fields so Sheet command versions can catch up; private note/reference text is never included in that export.

Refunds are limited to cancelled orders currently requiring a refund, cannot exceed the remaining total, and cannot have a completion time before order creation or after the server's current time. Amounts remain integer minor units in storage. The ledger sum determines the recorded balance; the UI cannot directly overwrite it.

## Privacy and deployment

Customer erasure and scheduled retention scrub note bodies and refund references while retaining restricted event metadata and refund amounts. Notes cannot be added to anonymized orders. Financial reconciliation can continue, but a new reference is not retained. Command idempotency records contain a content fingerprint and result metadata, not clear-text notes/references.

Migration `0003` creates the indexed `order_activity` table and revokes access from PostgreSQL PUBLIC and any existing `anon`/`authenticated` roles. The local SQLite database was backed up before upgrading. Apply the migration once on the target environment before starting the matching API/worker.

Drain/stop the old worker and promote compatible API and worker revisions together. Readiness requires `0003`; older releases requiring exactly `0002` are not a compatible application rollback target. Prepare a `0003`-compatible rollback build or roll forward. The migration refuses a destructive downgrade while refund records exist. Backups must include the ledger, and restores must preserve it alongside order/payment status.

No existing provider credentials, payment rails or real customer accounts were used for validation.
