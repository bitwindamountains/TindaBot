# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Customers:** Filipino shoppers who message a seller's Facebook Page in Messenger, usually on mobile and with little patience. They write in English, Tagalog, or Taglish and want to know the price and get an order placed in under two minutes. They never see the web workspace.
- **Seller and staff:** a small PH business (clothing, food, beauty, pre-loved items) with basic smartphone and Google Sheets skills. They use the seller workspace for daily order work: confirming orders, checking payments, adjusting stock, packing and shipping, and picking up chats handed over by the bot.
- **Operator:** the person who deploys and configures TindaBot. They work in the same workspace on automation controls, delivery recovery, diagnostics, and tokens.

The seller workspace at `/` serves seller staff and the operator equally, as one interface.

## Product Purpose

TindaBot is a Messenger ordering service for one Facebook Page. It answers repetitive questions instantly ("hm po?", "avail pa?", "COD?"), shows the catalog, takes complete orders through guided checkout, tracks orders, and hands a conversation to a human when needed. Every order lands in PostgreSQL and a Google Sheet the seller already knows how to use.

Success means no lost orders, complete order details every time, fewer repeated questions for the seller, and the seller stepping in only when it matters.

## Positioning

A deterministic, auditable order taker, not an AI chatbot. FAQ matching uses explicit keywords. Checkout is a state machine. Inventory is allocated atomically. Delivery is durable and idempotent. Sellers keep Google Sheets as a working fallback (the Commands tab), and human takeover is explicit, so the bot never talks over the seller.

## Operating Context

- Customers use Messenger, within Meta's 24-hour messaging window.
- Sellers use the Google Sheet (Products, FAQ, Orders projection, Commands), seller email notifications, the Facebook Page inbox for handovers, and the seller workspace.
- Payments happen outside the system: COD, GCash, or bank transfer instructions. Refunds are tracked as external references.
- Scale: one Page, 10 to 500 conversations a day.
- Status: a locally verified release candidate headed for a **supervised pilot with a real seller Page**. Not yet deployed or approved for public orders.

## Capabilities and Constraints

- Implemented: webhook intake with signature checks; Taglish FAQ; catalog carousel; guided checkout (delivery or pickup, PH phone validation, version-tied confirmation); atomic inventory; order tracking; human handover queue with version-checked resume; seller workspace (Overview, Orders, Inventory, Automation) with notes and history, external-refund tracking, stock adjustments, CSV export, a global automation switch, and delivery recovery.
- Workspace credentials stay in tab memory only. Status-only tokens cannot read customer data. When no operator is connected, the public shell shows **labeled sample data**.
- The default `dry_run` mode sends nothing. Shipping, pickup, and payment settings are deploy-time configuration in this release.
- Out of scope: online payment processing, card data, AI free chat, courier integrations, multi-Page SaaS.
- Deferred: payment-proof upload, proactive status messages, fuzzy FAQ matching, a seller-editable Settings tab.
- Terminology: order code, SKU, Commands tab, handover, automation pause/resume, dry run.

## Brand Commitments

- Name: **TindaBot**.
- Workspace UI language: **English**. Taglish belongs only in customer-facing Messenger replies.

## Evidence on Hand

- Validation screenshots and test reports: `docs/validation/`. Local load report: `docs/validation/local-load.json` (internal processing only, no real Messenger delivery).
- Design audit and incumbent design system: `docs/DESIGN_SYSTEM.md`. Release state: `docs/RELEASE_STATUS.md`.
- None yet: real customers, testimonials, seller case studies, pilot results, or production metrics. Do not fabricate them. Sample data must stay labeled as sample.

## Product Principles

1. **Never lose or invent an order.** Truth lives in the database. The UI shows what is real and labels what is sample or uncertain.
2. **The seller stays in control.** The bot yields on handover, pauses conservatively, and resumes only by explicit action.
3. **Meet sellers where they already work.** Messenger, Sheets, email, and a phone come first. The workspace adds to them and doesn't replace them.
4. **Make risky actions explicit.** Status changes, stock adjustments, refunds, and delivery recovery are confirmed, version-checked, and auditable.
5. **Two users, one tool.** Daily seller tasks stay simple and visible. Operator diagnostics stay available without crowding them.

## Accessibility & Inclusion

- Keyboard-operable workspace with accessible dialogs, a command palette (Ctrl/Cmd+K), and a keyboard-accessible chart.
- Light and dark themes. Ambient motion respects reduced-motion settings, can be paused, and falls back to lightweight CSS on mobile, data-saver, and devices without WebGL.
- Mobile layouts are first-class because sellers work from a smartphone.
