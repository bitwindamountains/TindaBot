# Progress

Last updated: 24 November 2026 · Latest commit: `9b8eddf` · CI: [run 45188274476](https://github.com/bitwindamountains/TindaBot/actions/runs/45188274476) passed

## Status

**Code: ready for staging. Public demo live at https://tindabot.onrender.com.** Staging and production are not deployed. Production also needs real provider accounts, a hosted rehearsal, privacy sign-off and a supervised pilot (see "Next steps").

Validation at `9b8eddf`: CI passes every step (183 Python tests including PostgreSQL, 36 Playwright tests, `pip-audit`, `npm audit`, wheel smoke, container API/worker readiness), the Render Blueprint validates, and the schema remains `0003`.

## Done in the 23 November 2026 session

Pre-deployment review: lint/format clean, 161 Python tests pass (19 PostgreSQL tests CI-only), 36 Playwright tests pass. A scripted end-to-end run (signed webhook → worker → dry-run outbox) confirmed FAQ, typed cart and checkout, order and stock allocation, tracking, opt-in shipped update with note, STOP handover, and auth/signature rejection.

Added a deployable public demo: `DEMO_MODE` (refused with production or live delivery), public read-only `POST /demo/test-chat` sharing the operator test chat, showcase catalog matching the browser preview, and `render.demo.yaml` (one free web service, SQLite, no secrets). See `docs/DEPLOYMENT.md` → "Public demo".

| Area | What changed | Commits |
|---|---|---|
| Demo mode | `DEMO_MODE`, `/demo` flag, `/demo/test-chat`, showcase seed, `render.demo.yaml`, docs | `1bc20a7` |
| Dependencies | `pip-audit` advisories fixed: certifi, filelock, oauthlib, opentelemetry-api, pyasn1 upgraded in `uv.lock` | `7c326c3` |
| Tooling | uv 0.12.21 → 0.13.4 (PYSEC-2026-4321) in CI, Dockerfile and both blueprints | `7e15557` |
| CI | Actions moved to Node 24 majors (checkout v5, setup-uv v7, setup-node v5, upload-artifact v6) | `1e33348` |
| Matching | A product's last name word alone now picks it ("2 mugs po", "candle po"); other single name words still need a second match, so "good morning" stays a greeting. Reviewed the demo locally with the blueprint start command: health, auth gates, full chat checkout, read-only confirm, browser chat under CSP | `9b8eddf` |

**Demo deployed (24 November 2026):** https://tindabot.onrender.com, a free Render web service created by hand in the dashboard with the values from `render.demo.yaml` (the Blueprint flow asked for a card that was declined; Hugging Face Docker Spaces now need PRO). It auto-deploys `main`. Verified live: `/readyz` ready, `/demo` enabled, `/docs` 404, admin 401, webhook 403, CSP headers, chat FAQ/checkout/over-stock/handover/tampered-quote, browser chat with no console errors. Keep the service's settings in step with `render.demo.yaml` by hand.

## Done in the 19 October 2026 session

| Area | What changed | Commits |
|---|---|---|
| Product context | `PRODUCT.md` written | `ea1b3c9` |
| Workspace polish | Focus ring, short-list numbering, mobile filter fade, type roles (11px/12px minimum), short list first on narrow screens, order-progress count roll, stage-specific toasts, tablet metric wrapping | `ea1b3c9`, `892a780`, `710c80e` |
| Audit fixes | One-pass retention, Sheet pause/resume via handover rules, readable Sheet values, Manila order-code date, ID-column-only Sheet export | `20d916b` |
| Automation insights | Self-serve rate, missed-question list, Add to FAQ row | `9da5162` |
| Bot understanding | Plain-language intents, product names with quantities, typed checkout answers, mid-checkout questions, FAQ precedence, FAQ topic list. Measured 24/45 → 40/45 opening messages, 3/12 → 12/12 typed checkout answers | `d3c451c` |
| Test chat | Read-only "Talk to your bot" sharing `apply_actions()` with live messages | `cf99255` |
| Order updates | Opt-in confirmed/shipped/delivered/paid messages, optional shipping note | `d127e4f` |
| Release review | Fixed: handover false positives, sizes read as quantities, compound Tagalog numbers, blank FAQ rows, updates after STOP, test-chat resource exhaustion, status-token notes, blocked reply lanes | `482ccfa`, `5949d71` |
| Cleanup and docs | Retired post-purchase tag path removed (updates only within 24h, sent as `UPDATE`); old Sheet headers upgraded in place; README, release status, deployment handoff updated | `68433de` |

Plan for the automation work: `docs/ideas/automation-teaching-loop.md` (steps 1–4 built).

## Next steps (owner: you)

1. **Accounts:** Meta test Page + app (Page ID, App ID, App secret, Page token, verify token), Google Sheet + service account (base64 JSON key), SMTP sender, PostgreSQL database, public privacy notice URL.
2. **Staging on Render:** New → Blueprint from this repo; fill the `tindabot-production` environment group (see `.env.example`); set `APP_ENV=development` and `DELIVERY_MODE=dry_run` for staging (production settings refuse dry-run); generate `ADMIN_TOKEN` and `STATUS_TOKEN` with `uv run tindabot new-token`; deploy `1e33348`; check `/readyz`, workspace Connect, worker heartbeat.
3. **Connect providers:** Meta webhook `https://<app>/webhook`; `tindabot setup-sheet` and `tindabot setup-profile`; fill Products and FAQ; switch to `live`; test browse, checkout, tracking, handover, seller email, Sheet row.
4. **Before real customers:** backup/restore and rollback rehearsal (`docs/OPERATIONS.md`), privacy and retention approval, one-week supervised pilot with the seller, then `PRODUCTION_ACKNOWLEDGED=true`.

## Open questions

- Order-update copy is English; should it be Taglish?
- Missed questions group only by exact normalized wording; does pilot data show Taglish spelling variants that need looser grouping?
- Should the self-serve rate also count seller-initiated pauses (Page replies) as "needed you"?
- Should order updates wait while the seller is handling a chat? Currently they are sent unless the customer sent STOP.

## Known limits

- The public demo chat's per-visitor limit trusts `X-Forwarded-For`, which a client can forge; only the overall cap (300 messages a minute) reliably bounds load.
- The demo's free Render plan sleeps after ~15 minutes idle; the first visit after that takes about a minute.

- Plain-language rules are informed guesses for English/Taglish; confirm against pilot data from the missed-question list.
- Refused order updates are suppressed (so they never block replies) and therefore don't appear in the health failure count.
- Physical-device mobile performance and non-Chromium browsers remain unverified.
