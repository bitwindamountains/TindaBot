# Handover review and fixes

Reviewed 8 October 2026 against checkpoint `786a1bd`. Scope: handover creation, pause/resume, privacy erasure, pending-event processing, queue reads and the browser confirmation flow. No feature expansion or database migration.

| Severity | Finding and trigger | Fix | Regression evidence |
| --- | --- | --- | --- |
| P1 | A customer sends STOP, then an external Page reply, operator pause or SELLER request replaces the marker reason. The UI loses the customer-consent wording. Repeated pauses also reset the original waiting time. | Preserve STOP and the existing handover start time while the conversation remains paused. Customer MENU or an explicit operator resume clears the marker, allowing a new handover afterward. | Backend regression failed with reason `customer` before the fix; now verifies STOP survives all three pause paths and a later new handover can use `customer`. |
| P1 | A message/echo has been durably received but not processed. Its conversation version is unchanged, so an old dialog can resume the bot before the operator sees the new activity. Failed incoming work has the same gap. | Under the existing conversation row lock, reject resume while pending or failed inbox events exist. Keep pause/version untouched. The workspace explains that the worker needs attention. | Message, echo and failed-event regressions each returned 200 before the fix; now require 409 and verify a fresh resume succeeds after processing. Cases also run on PostgreSQL. |
| P2 | Resume returns success, then the queue reload fails. The old confirmation form remains actionable and reports a generic failure, despite the mutation already being saved. | Show a saved-state screen immediately after success. Refresh failures explicitly say the resume was saved and offer a queue refresh without another mutation button. | Browser regression reproduced the misleading failure before the fix. It now confirms saved wording, no resume button, successful refresh recovery and exactly one mutation request. |

Existing documented limits remain: pre-update unmarked pauses are not backfilled; the external link opens the Page inbox rather than a verified individual thread; live Meta account acceptance is outstanding. This review does not certify the entire application or its external integrations.

Validation: [full backend run](validation/handover-review-backend-tests.xml), [targeted browser regressions](validation/handover-review-browser-tests.json), [full browser suite](validation/ui-tests.json) and [installed-package smoke](validation/release-smoke.json).
