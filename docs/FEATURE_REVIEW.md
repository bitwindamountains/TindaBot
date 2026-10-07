# Feature review

Reviewed 7 October 2026. Scope: the seller workspace and the API contracts it uses. The current deployment target remains a single privileged operator and one seller.

## Changes completed

| Finding | Improvement | Verification |
| --- | --- | --- |
| Live order details omitted the creation date used by the drawer. Sample and mocked records hid this mismatch. | The protected detail endpoint now supplies `created_at`. Older payloads display “date unavailable” while keeping the order usable. | API assertion against a real checkout; browser regression for the older payload. |
| Fulfillment status alone did not identify unpaid orders or refunds requiring follow-up. | Independent payment filtering, visible payment labels, oldest-first sorting, and payment status in the filtered CSV export. Clearing filters resets both status and payment. | Browser workflow verifies payment, cancellation, refund filtering, and the actual CSV contents. |
| Sellers had to scan every product to find empty shelves or inactive items. | Out-of-stock and inactive views, plus sorting by stock, name, or price. Low-stock counts explicitly refer to the loaded catalog. | Browser workflow removes the last units, finds the product in the out-of-stock view, and checks sorting. |
| Signed stock changes were difficult to check before saving. | Add/remove shortcuts and an announced before/after estimate. An excessive removal is explained before submission; the preview and input also respect the API limit of plus or minus 1,000,000 units. Live adjustments still apply against current server stock and retain their retry command ID. | Preview, invalid-removal, empty-stock, accessibility, and existing live-write retry tests. |
| Automation showed aggregate numbers without explaining the next step. | Separate failed incoming events, failed deliveries, and uncertain deliveries; snapshot status and guidance for a stale worker, server lock, paused replies, or dry-run delivery. | API counts and connected browser diagnostics in both themes. |

Payment verification records an operator's confirmation; it does not charge a customer. Refund filtering identifies follow-up work; it does not issue a refund. Diagnostic guidance does not retry or suppress jobs automatically.

## Next priorities

| Priority | Gap | Concrete next increment / acceptance criteria |
| --- | --- | --- |
| P1 | Order browsing is limited to the latest 200 records in a 7/30-day window. | Add authenticated server search and cursor pagination, an explicit date range, stable ordering, and export of the selected result set. Verify timezone boundaries, insertion during pagination, and access protection. |
| P1 | A refund can be flagged, but its external completion cannot be recorded in the workspace. | Add a version-checked, idempotent refund-reconciliation action with an audit record and reference. Distinguish recording an external refund from sending money. |
| P1 | Diagnostics describe problems; reconciliation still needs the operator runbook. | Add a protected job inspection screen with bounded, redacted error details. Retrying an uncertain result needs an explicit duplicate-delivery acknowledgement and an audit record. |
| P1 | Real Meta, Sheets, SMTP, and hosted deployment acceptance are outstanding. | Run the documented staging and supervised-seller checks with the actual accounts. A heartbeat alone must never be presented as end-to-end delivery success. |
| P2 | Product creation, catalog import, and availability edits depend on the seller Sheet/API. | Build an import preview showing valid rows, row errors, and stock effects before applying. Preserve the existing atomic catalog rules. |
| P2 | One operator credential is shared by the workspace. | Before adding staff, introduce individual sessions, role checks, revocation, and attributable audit events. Do not add cosmetic role selectors without server enforcement. |
| P2 | No physical-device or non-Chromium acceptance yet. | Verify Safari/Firefox, a mid-range phone, assistive technology, and motion battery cost. Keep the mobile/reduced-motion fallback. |

The completed changes improve the current single-seller workflow. The remaining items above are not implied to be implemented or verified by the current release candidate.
