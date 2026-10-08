# Delivery recovery

In Automation, select **Review deliveries** to inspect failed and uncertain outbound jobs. The newest 50 appear first; **Load earlier deliveries** retrieves older entries. Refresh explicitly to check for changes. Incoming event failures remain an operator/runbook workflow.

Each entry shows the channel, job ID, attempt count, creation time in Manila, a safe error code and guidance. The response excludes message bodies, customer identities, recipient addresses, business keys and raw exception text. Unknown errors become `delivery_error`. Reads require the operator credential and use `Cache-Control: no-store`.

Check the provider and correct the cause before choosing **Review retry**. Uncertain deliveries may already have succeeded: the workspace requires explicit acceptance of duplicate-delivery risk. Retrying queues work; it does not confirm successful delivery. The worker still applies privacy, automation and delivery-window checks. Suppression prevents further attempts for that job and does not undo anything already delivered. There is no bulk retry.

`GET /admin/workspace/jobs` accepts optional `status=all|failed|uncertain` and `before=<job ID>`. Pagination is bounded and reflects current state, not a frozen historical snapshot.

`POST /admin/jobs/{id}/resolve` retains its existing action/acknowledgement contract and adds optional `command_id` and `expected_revision`. The workspace always supplies both. A row lock serializes resolution with dispatch and erasure. A stale snapshot is rejected. Identical command retries return the original result even if the worker subsequently fails again; changed content with the same command ID is rejected. Legacy runbook callers without these fields retain the earlier behavior.

Each successful resolution appends a restricted `audit:*` record with job ID, prior status, action, attempt count, shared Operator role and duplicate-risk acknowledgement; `updated_at` records the timestamp. Idempotent response retries do not add audit entries. Audits remain available to database operators; this screen is a queue, not an audit-history browser. No individual staff identity is implied by the shared operator credential.

No schema migration is needed beyond `0003`. Promote matching API and static assets together. This increment does not perform live provider acceptance or public deployment.
