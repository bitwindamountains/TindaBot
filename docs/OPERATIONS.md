# TindaBot operations

## Release procedure

1. Record the revision and build artifact. Run CI, dependency audit, PostgreSQL concurrency tests, and staging acceptance.
2. Confirm the API and worker use the same database, Page, Sheet, and behavior settings. Use separate development/staging/production credentials.
3. Back up the database using a direct/session connection. Confirm the last successful restore drill and deletion-ledger export.
4. Deploy the API with one Alembic pre-deploy migration. Wait for `/readyz` before deploying the worker. Do not run migrations from every worker start.
5. Check worker age and queue delay through `/admin/health`; run a permitted test order and verify DB, Sheet, seller notification, and customer receipt.
6. Enable public Page traffic only after Meta access and the launch checklist are complete. Observe the five-business-day pilot.

Render automatic deploys are disabled in the template. Production migrations should remain backward compatible with the previously deployed code. Application rollback uses the previously tested revision; do not run destructive Alembic downgrades against production as a routine rollback.

## Monitoring

Run `uv run python scripts/check_health.py` from an independent monitor every minute, with `TINDABOT_URL` and `ADMIN_TOKEN` supplied securely. Connect nonzero exits to an actual operator notification channel. The script itself does not deliver alerts, and this external monitoring integration remains a launch requirement.

Watch failed/uncertain jobs, worker silence, inbox age, Sheet synchronization errors, PostgreSQL storage/connections, and token errors. The worker heartbeat is a liveness indicator, not proof that each integration is healthy. Invalid Meta credentials turn off automation in persistent DB control state; fix credentials and explicitly re-enable after verification.

JSON logging uses static event/error codes and selected job IDs. API access logs are disabled in deployment commands. Never enable SQL parameter logging, raw webhook logging, or full HTTP request/response logging in production.

## Queue recovery

`uv run tindabot jobs` lists failed/uncertain work without customer payloads.

| Condition | Response |
|---|---|
| Inbox event failed repeatedly | Fix the cause, inspect authorized data privately if needed, then `uv run tindabot retry-event EVENT_ID`. Later events for that customer wait behind it. |
| Messenger/SMTP result uncertain | Inspect provider/Page/seller evidence. If already delivered, suppress the job. If a retry is appropriate, explicitly accept possible duplicate delivery through the operator endpoint. |
| Sheet append uncertain | The worker searches stable order IDs before retrying. Duplicate IDs stop export; reconcile rows before resolving the job. |
| Invalid Meta token | Rotate/configure credentials, verify Page permission, redeploy affected processes, resolve affected jobs, and re-enable automation. |
| DB unavailable | API returns 503 instead of acknowledging unpersisted events. Restore access and watch redelivery/queue drain. |
| Sheet unavailable | Orders remain in PostgreSQL; stale catalog eventually blocks new checkout. Fix access/quota/configuration, then reconcile backlog. |

Resolve outbox jobs using `POST /admin/jobs/{id}/resolve` with `{"action":"suppress"}` or `{"action":"retry","accept_duplicate_risk":true}` and the operator bearer token. These actions are recorded in the DB audit. A blocked job halts later jobs in that destination lane until resolved.

Use `POST /admin/automation` with `{"enabled":false}` to disable automatic conversation handling/sending. Webhook intake continues. Use `POST /admin/conversations/{psid}/pause` with `{"enabled":true}` for one customer. Keep PSIDs out of public tickets and access logs.

## Backup and restore

Install PostgreSQL client tools of the same or newer major version as the source server. Supply `BACKUP_DATABASE_URL` privately in the environment; use a direct or session connection. The script places passwords in child-process environment variables, not command arguments.

```powershell
uv run python scripts/database_backup.py backup backups/orders-YYYYMMDD.dump
```

The output contains personal data. Restrict local access and transfer backups to approved encrypted storage with documented expiry. This repository does not automatically upload or encrypt backup files. Schedule backups to meet the agreed RPO; the plan's 24-hour proposal is not automatically acceptable for every seller.

For a drill, create a **separate empty database** and set `BACKUP_DATABASE_URL` to that target:

```powershell
uv run python scripts/database_backup.py restore backups/orders-YYYYMMDD.dump
```

Restore deliberately omits `--clean`, stops on errors, and must not target the live database. Verify migration version, table counts, order totals, ownership checks, and job states. Reapply current DB role restrictions. Do not start a live worker on a restored clone: historical outbox jobs could send duplicate notifications.

Before using a restored database in production, replay deletion/erasure records newer than the backup, reconcile provider deliveries and Sheet order IDs, and mark already-sent jobs appropriately. Keep an encrypted deletion ledger outside the database being restored. This export/storage process is an operator launch obligation.

The backup covers PostgreSQL only. Keep a separate controlled copy of seller-owned catalog/FAQ data. If proof storage is added later, add its own backup/retention policy.

## Privacy requests and retention

Verify the requester's identity and the seller's retention obligations before acting. Pause the conversation and wait for active deliveries to complete. `POST /admin/conversations/{psid}/erase` erases controlled personal fields and queues Sheet updates. Check that all Sheet erasure jobs actually finish; review email/provider/backups separately.

The endpoint retains restricted PSID/order association metadata and an erasure ledger. Full identity unlinking is not implemented and must not be promised. Export the ledger securely before backup expiry or restoration. Failed erasure jobs are operational incidents, not successful deletion.

Worker maintenance runs every minute: clears old checkout context, removes old event/reply text, anonymizes order fields after the configured period, and cancels expired unpaid orders with one stock release. Retention periods and reservation expiry must be seller-approved before production acknowledgement.

## Seller onboarding

The web workspace is served at `/` on the API origin. Connect using `ADMIN_TOKEN` over HTTPS; a status-only token cannot read customer data. Tokens stay in tab memory and are cleared on reload/disconnect. Default preview data is fictional and browser-only. All connected mutations affect the real database even when delivery is `dry_run`.

Use **Orders** to inspect a record before confirming, marking payment received, shipping, or cancelling. Payment confirmation records the operator's verification and does not charge the customer. Cancelling a paid order flags a refund requirement; the actual refund is handled outside the app. **Inventory → Adjust stock** takes a signed quantity, applied against current stock. If the request fails after a possible write, retry in the same dialog to reuse its command ID; reconcile stock before opening a new adjustment.

Order value includes shipping and unpaid orders and excludes cancelled orders. It is not settled revenue. Reports use Manila calendar days; the UI labels capped results and exports only loaded filtered rows. **Automation** reports the snapshot's worker heartbeat, queue state, and effective server-controlled automation state.

Protect all Orders columns and the Commands result column; share with only authorized staff. Explain that Products stock is initial inventory, not a replenishment control. Record stock reserved for this bot when the seller sells through other channels. Use idempotent operator inventory adjustments for replenishment and external sales.

Train staff on unique command IDs, expected versions, paid versus fulfillment state, rejected commands, Page-inbox takeover, and `MENU` returning the customer to automation. A screenshot or payment instruction never marks an order paid automatically.


### Workspace follow-up views

- In Orders, combine fulfillment and payment filters to review unpaid orders or refunds requiring follow-up. CSV exports exactly the loaded, filtered rows and includes payment status. It is not a full-history export.
- In Inventory, sort by lowest stock or select Out of stock / Inactive. Adjustment shortcuts only fill the quantity; Save adjustment submits it. The estimate uses the displayed snapshot, while the server applies the signed adjustment against current stock. Each adjustment is limited to plus or minus 1,000,000 units.
- Automation shows a snapshot and conditional next steps. Failed incoming events, failed outbound jobs, and uncertain deliveries are separate signals. Follow the reconciliation process above before retrying uncertain deliveries. A recent heartbeat does not certify provider delivery.
