# Progress

Last updated: 19 October 2026 · Latest commit: `68433de` · CI: [run 39212795675](https://github.com/bitwindamountains/TindaBot/actions/runs/39212795675) passed

## Status

**Code: ready for staging.** Not yet deployed. Production also needs real provider accounts, a hosted rehearsal, privacy sign-off and a supervised pilot (see "Next steps").

Validation at `68433de`: 158 Python tests pass locally (19 PostgreSQL tests run in CI only), 35 Playwright browser tests pass, `pip-audit` and `npm audit` report no vulnerabilities, the Render Blueprint validates, and the schema remains `0003`.

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
2. **Staging on Render:** New → Blueprint from this repo; fill the `tindabot-production` environment group (see `.env.example`); set `DELIVERY_MODE=dry_run` for staging; generate `ADMIN_TOKEN` and `STATUS_TOKEN` with `uv run tindabot new-token`; deploy `68433de`; check `/readyz`, workspace Connect, worker heartbeat.
3. **Connect providers:** Meta webhook `https://<app>/webhook`; `tindabot setup-sheet` and `tindabot setup-profile`; fill Products and FAQ; switch to `live`; test browse, checkout, tracking, handover, seller email, Sheet row.
4. **Before real customers:** backup/restore and rollback rehearsal (`docs/OPERATIONS.md`), privacy and retention approval, one-week supervised pilot with the seller, then `PRODUCTION_ACKNOWLEDGED=true`.

## Open questions

- Order-update copy is English; should it be Taglish?
- Missed questions group only by exact normalized wording; does pilot data show Taglish spelling variants that need looser grouping?
- Should the self-serve rate also count seller-initiated pauses (Page replies) as "needed you"?
- Should order updates wait while the seller is handling a chat? Currently they are sent unless the customer sent STOP.

## Known limits

- Plain-language rules are informed guesses for English/Taglish; confirm against pilot data from the missed-question list.
- Refused order updates are suppressed (so they never block replies) and therefore don't appear in the health failure count.
- The installed-wheel smoke test (`scripts/smoke_release.py`) was not re-run in this session (no network for a clean environment).
- Physical-device mobile performance and non-Chromium browsers remain unverified.
