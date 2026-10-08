# Human handover queue

Open **Customers needing help** from Overview or Automation. The count and list show tracked conversations whose bot replies are paused. Each entry shows the available checkout/order name, pause reason and last customer message time in Manila. No message transcript, phone number or address is exposed. Refresh explicitly for current data; pages contain at most 50 entries.

Use **Open Page inbox** and select the correct shop and conversation in Meta Business Suite. This is an inbox link, not a direct thread link: no verified mapping from the stored Page-scoped ID to a browser thread URL is implemented. Names are customer-supplied checkout/order names, not verified Facebook profile names. A short reference distinguishes records locally; it is not a searchable Messenger identity. [Meta describes Business Suite's messaging workflow](https://about.fb.com/news/2020/09/a-faster-and-easier-way-to-manage-your-business-on-facebook-and-instagram/).

After handling the request, choose **Review resume**, confirm, and select **Resume bot**. STOP requests explicitly require confirming the customer wants bot replies again. Resuming sends no message and still respects the shop-wide automation setting. If another message or pause arrives while the dialog is open, the version check rejects the stale action; return and refresh. A lost response can also produce this conflict on retry: refresh to see whether the first resume succeeded.

## Deliberately small scope

- Uses the existing conversation pause flag, version and JSON context. No new table, migration, chat system, assignment system or provider API request.
- New SELLER/AGENT/TAO/TALK_TO_SELLER and STOP requests, detected external Page replies and operator pauses create a small handover marker. Explicit requests are tracked even while global automation is disabled. Existing customer MENU/GET_STARTED behavior resumes the bot and removes the marker.
- Draft expiry discards personal draft fields but preserves the pause marker. Customer erasure clears the marker and increments the conversation version so an open resume dialog cannot reverse erasure's pause.
- **Rollout limit:** pauses created before this update have no marker and are not retrospectively listed. They remain paused. Review existing pauses through the operator runbook; explicitly pausing one again records it in the new queue. Counts refer to tracked handovers, not all paused conversations.
- Names can become unavailable after draft expiry or erasure. There is no Facebook profile lookup or message-content search to compensate for missing identity.

## API and validation

`GET /admin/workspace/handovers?after=<cursor>` is operator-only, Page-scoped and `no-store`. It supplies the next cursor when more entries exist. `GET /admin/workspace` includes `handover_count`. The existing `POST /admin/conversations/{psid}/pause` accepts optional `expected_version`; the workspace always supplies it. The conversation row lock serializes resume with message processing and erasure. Legacy API clients may still omit the version.

Backend checks cover access control, pagination, Page isolation, stale resume, erasure, draft expiry, global automation off, customer MENU, external echoes and no message sent by resume. Browser checks cover confirmation, STOP wording, stale-state refresh, escaping, pagination, count updates, mobile overflow and both themes. Installed-package smoke verifies the new asset and queue/resume API. Real account inbox matching remains part of supervised seller acceptance.
