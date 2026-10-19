# Automation: the teaching loop

## Problem Statement

How might we make the Automation page a place where the seller can see what the bot handled, teach it what it missed, and keep customers informed, without giving up the deterministic, auditable bot?

## Recommended Direction

Turn the page from a status board into a weekly improvement loop, built in this order: **measure → teach → reach out → check**.

1. **Measure (idea 7).** The page leads with one sentence: "Today TindaBot handled **41 of 52** conversations on its own. **8** needed you. Here are the **3 questions** it couldn't answer." The headline number is the **self-serve rate**: conversations a day with customer activity and no fallback reply and no handover. Operator diagnostics (heartbeat, delivery queue, delivery recovery) move into a clearly separated section below.
2. **Teach (idea 1).** List every message that got the fallback reply, grouped by exact normalized text with a count. "Add to FAQ" prepares a keyword and answer to paste into the Sheet's FAQ tab and links to it. The 60-second Sheet sync picks the row up. No new write path.
3. **Reach out (idea 2).** Switches for customer messages on Confirmed, Shipped (with an optional tracking note), Delivered and Payment received, sent through the existing Messenger outbox. In `dry_run` they are recorded as "would send".
4. **Check (idea 5).** A "Talk to your bot" test chat running the real conversation logic in dry-run against today's catalog and FAQ. It ships only after the quote/confirm handling in `service.py` moves into one function shared by the live path and the test chat.

This direction keeps the product's position: a rule-based bot that shows where it fails and gets measurably better, rather than guessing with AI. The seller keeps working in the Sheet, and the workspace tells them what to add.

## Key Assumptions to Validate

- [ ] **Misses are frequent and repeat.** Run the pilot for one week with only the `missed` flag recorded, then count total misses and repeats.
- [ ] **Exact normalized grouping is good enough for Taglish.** On that week's data, measure how many misses share an exact normalized text. If almost nothing groups, add keyword-overlap grouping before building the list UI.
- [ ] **Sellers act on the list.** Track FAQ additions and the self-serve rate for two weeks after the list ships.
- [ ] **Meta allows post-purchase updates outside the 24-hour window.** Check current Meta Messenger policy for the post-purchase update message tag in the Graph API version used, then send one tagged message on the test Page. This blocks step 3.
- [ ] **Order updates reduce "where's my order?" questions.** Compare misses mentioning shipping or delivery timing ("ship", "dating", "kailan") before and after step 3.

## MVP Scope

**In (steps 1–2):**
- Flag the inbound event when `transition()` increments `ctx["misses"]` (`payload["missed"] = true` on the `Inbox` row). Existing retention and erasure already scrub `Inbox.payload`, so no new store of personal data and no migration.
- A self-serve rate and miss list computed from `Inbox` for today and the last 7 days, in Manila time.
- The Automation page restructured: seller summary and miss list on top, operator diagnostics below.
- "Add to FAQ": copyable keyword and answer, plus a link to the FAQ tab.
- Tests: the flag is set on a fallback and not on an FAQ hit, and the rate counts handovers and misses correctly.

**Out of the MVP:** order-update messages (step 3, after the Meta check), the test chat (step 4, after the refactor), and writing to the Sheet directly.

## Not Doing (and Why)

- **AI-written replies or AI-suggested answers.** The product is deterministic by decision; the teaching loop gets the improvement without the risk.
- **A general "when X, do Y" rule builder.** Sellers rarely configure open-ended rules. Specific switches cover the real cases.
- **Editing FAQ inside the workspace.** The Sheet sync would overwrite it within a minute. The Sheet stays the source of truth until pasting proves to be friction.
- **Fuzzy or semantic grouping of misses.** Exact normalized grouping first. Add more only if the pilot data shows it fails.
- **Restock or marketing broadcasts.** These need separate Meta opt-in rules and are not order updates.
- **Moving shop settings (payment instructions, shipping fee, pickup address) out of deploy config.** Useful, but plumbing rather than automation. It stays a separate decision.
- **Proactive frustration-based handover (idea 6).** A good fit for later. It can reuse the same `missed` data once the loop exists.

## Open Questions

- Does Meta's post-purchase update tag still exist and cover order status messages in the Graph API version TindaBot targets?
- Should order-update messages use the bot's English copy or Taglish? Current bot replies in `messages.py` are English.
- What window should the miss list show by default: today, or the last 7 days?
- Should the self-serve rate count a conversation as "needed you" when the customer typed SELLER even though the bot understood everything?
