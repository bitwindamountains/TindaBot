# TindaBot

Deterministic Messenger ordering service for one Facebook Page: FAQ replies, product carousel, guided checkout, order tracking, seller handover, PostgreSQL inventory, Google Sheets operations, and a same-origin seller workspace at `/`. No AI answers, by design.

Product context: `PRODUCT.md`. Original spec: `03_TindaBot_Blueprint.md` (the code has moved past parts of it; see `docs/RELEASE_STATUS.md`). Current state and next steps: `PROGRESS.md`.

## Commands (Windows workspace)

- Install: `.venv/Scripts/uv.exe sync --frozen`
- Migrate: `.venv/Scripts/uv.exe run alembic upgrade head` (schema head is `0003`)
- Run API: `.venv/Scripts/uv.exe run uvicorn tindabot.main:create_app --factory --port 8000 --no-access-log`
- Run worker: `.venv/Scripts/uv.exe run tindabot worker`
- Refresh local sample catalog (stale after an hour without live Sheet sync): `.venv/Scripts/uv.exe run tindabot seed-demo`
- Lint/format: `.venv/Scripts/uv.exe run ruff check . && .venv/Scripts/uv.exe run ruff format --check .`
- Python tests: `.venv/Scripts/uv.exe run pytest -q` (PostgreSQL tests skip locally; CI runs them)
- Browser tests: `npx playwright test` (reuses a server already on port 8000; rewrites `docs/validation/*.png`)
- Full release gate: `docs/DEPLOYMENT.md` → "Local release gate"

## Where things live

- `src/tindabot/machine.py`: pure conversation transitions. No DB, HTTP or Sheets calls. Plain-language intents (`SELLER`, `TRACK`, `BUY`), `quantity()`, `faq_answer()`, `find_product()`.
- `src/tindabot/messages.py`: all customer-facing copy, including `order_update()`.
- `src/tindabot/service.py`: `process_one()` handles inbound events; `apply_actions()` performs quote/confirm/handover and is shared with the workspace test chat.
- `src/tindabot/orders.py`: orders, status changes, `queue_order_update()` (same transaction as the status change).
- `src/tindabot/worker.py`: job claiming, dispatch (24-hour window, STOP, lanes), maintenance/retention, Sheet sync.
- `src/tindabot/workspace.py`: workspace API, `automation_insights()`, `/admin/workspace/test-chat`.
- `src/tindabot/web/`: vanilla JS workspace (`app.js`, `demo.js` sample data, `studio.css` visual layer, `tokens.css`).

## Rules

- Keep `machine.py` pure and deterministic. Every behaviour change gets a test in `tests/test_machine.py`; new plain-language rules must not hijack checkout answers or hand over on ordinary words.
- Never skip webhook signature checks, idempotency keys, version checks or PSID ownership checks.
- Never log tokens, secrets, or unmasked customer name/phone/address.
- Customer-visible messages are sent only inside Messenger's 24-hour window. Meta retired the post-purchase tag; do not reintroduce message tags without verifying current Meta policy.
- Order updates never reach customers who sent STOP or whose data was erased. Only the operator token may add free-text customer notes; the status token may only change status.
- The test chat must stay read-only: it never commits, never trusts a browser-sent quote, and returns 4xx for malformed state.
- Per-customer data added to inbound payloads must stay inside `Inbox.payload` so retention and erasure remove it.
- Schema changes need an Alembic migration and a documented rollback target.
- Don't add dependencies without asking.

## Conventions

- When the browser suite refreshes `docs/validation/*.png`, commit them with the change.
- Throwaway capture specs in `tests/ui/` must be deleted after use; restore `docs/validation/ui-tests.json` if one overwrote it.
- Workspace design: ivory/ink/copper, Georgia display face, system sans body, tokens in `tokens.css`. Labels 11px, meta 12px minimum at every width. Respect reduced motion.
- Commit message trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
