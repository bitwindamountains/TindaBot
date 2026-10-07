# TindaBot — Project Blueprint

**Project 3 of 4 · Facebook Page / Messenger order bot**
Version 1.0 · October 2026 · Status: ready to build

> Stop drowning in "hm po?" messages. TindaBot answers FAQs, shows products, takes orders in Messenger, and logs every order to a Google Sheet the seller already knows how to use.

---

## How to use this blueprint with Claude Code

1. Create an empty project folder and save this file as `docs/BLUEPRINT.md`.
2. Copy the CLAUDE.md starter from **section 20** into `CLAUDE.md`.
3. Build one phase at a time from **section 18**. Your first milestone is an **echo bot** working through a tunnel (end of Phase 1).
4. `/clear` between phases.
5. Build TindaBot **before** PostPilot. Both use the Meta Graph API, so the Meta app setup you learn here carries over.

---

## 1. Product definition

| | |
|---|---|
| **What it is** | A Python web service that receives Messenger events from a Facebook Page, replies automatically, runs a guided ordering flow, and records orders in a database and a Google Sheet. |
| **Problem** | Online sellers get dozens of repetitive messages ("hm", "avail pa?", "COD?", "saan location?"). Replies are slow, orders get lost in chat, and details are incomplete. |
| **Value** | Instant replies 24/7, complete orders every time, one Sheet with all orders, and the seller only steps in when needed. |
| **Platform** | Web API (FastAPI) hosted on Render; customers use Messenger; seller uses Google Sheets + email. |
| **Expected scale** | 1 Page, 10–500 conversations/day. |
| **Authentication** | Customers: identified by Messenger PSID (no login). Seller: Google Sheet sharing. Operator: admin token for admin endpoints. |
| **Real-time** | Yes (replies within seconds). |
| **Offline** | No. |
| **Notifications** | Yes: seller email per order; customer messages within Meta's 24-hour window. |
| **Payments** | No payment processing. COD, GCash, or bank transfer instructions + proof upload (V1). |
| **Admin panel** | No custom panel. The Google Sheet *is* the seller's admin panel. |

### Assumptions
- Sellers are small PH businesses (clothing, food, beauty, pre-loved items) using a Facebook Page.
- Customers write in English, Tagalog, and Taglish.
- One flat shipping fee (or pickup) is enough for MVP.
- For demos you use your own test Page in Meta's development mode, which doesn't need App Review.

---

## 2. Goals and non-goals

**Primary goals**
- Answer common questions instantly (price, availability, shipping, COD, location, hours).
- Show products from a Google Sheet catalog as a Messenger carousel.
- Take complete orders: items, quantity, delivery method, name, phone, address, payment method.
- Save orders reliably and notify the seller.
- Let customers reach a human and pause the bot for that customer.
- Let customers track order status.

**Secondary goals**
- Payment proof upload, order status notifications, stock tracking, returning-customer prefill.

**Non-goals**
- Online payment processing or storing card data.
- A custom web dashboard (use Sheets).
- AI free-chat in MVP.
- Courier integrations.
- Multi-Page SaaS in MVP.

---

## 3. Users, roles, and permissions

| Persona | Who | Goal |
|---|---|---|
| **Customer "Joy"** | Buys via Messenger on mobile, low patience | Get price and order in under 2 minutes |
| **Seller "Aling Rosa"** | Owns the Page, basic smartphone + Sheets skills | Orders organized; fewer repeated questions |
| **Seller staff** | Packs and ships | Clear list of confirmed orders |
| **Operator (you)** | Developer | Deploy, configure, rotate tokens |

### Permissions matrix

| Capability | Customer | Seller / staff | Operator |
|---|---|---|---|
| Browse products, ask FAQs | ✅ | ✅ | ✅ |
| Place an order | ✅ | — | Test only |
| Track **own** orders | ✅ (own PSID only) | — | ✅ |
| See all orders | ❌ | ✅ (Sheet) | ✅ |
| Change order status | ❌ | ✅ (Status column) | ✅ |
| Edit catalog / FAQ / settings | ❌ | ✅ (Sheet) | ✅ |
| Pause/resume bot for a customer | Request via "Talk to seller" | ✅ (V1: auto-pause when seller replies) | ✅ admin endpoint |
| Deploy, tokens, secrets | ❌ | ❌ | ✅ |

**Least privilege:** the service account can edit only this one Sheet; admin endpoints require a bearer token; customers can never read other customers' orders.

---

## 4. Features

### MVP (P0)
| ID | Feature | Summary |
|---|---|---|
| F1 | Webhook foundation | GET verification, POST events, signature check, fast 200 response |
| F2 | Messenger profile | Get Started button, greeting, persistent menu (Shop, Track order, FAQ, Talk to seller) |
| F3 | FAQ auto-replies | Keyword + fuzzy intent matching (EN/Tagalog/Taglish) from the FAQ tab |
| F4 | Catalog browsing | Products tab → carousel (≤ 10 cards per carousel, "More" button to page) |
| F5 | Cart + checkout flow | State machine: product → qty → cart → delivery → name → phone → address → payment → confirm |
| F6 | Order persistence | DB transaction + Sheet row + order code |
| F7 | Seller notification | Email per new order (SMTP) |
| F8 | Human handover | "Talk to seller" pauses the bot for that customer for N hours |
| F9 | Order tracking | "Track" shows status of the customer's own recent orders |
| F10 | Reliability | Idempotency by message ID, per-customer rate limit, fallback replies |

### V1 (P1)
| ID | Feature | Summary |
|---|---|---|
| F11 | Payment proof | Customer sends GCash screenshot → stored (Supabase Storage) → linked in Sheet |
| F12 | Status notifications | Seller changes Status → customer notified (within the 24-hour window) |
| F13 | Stock control | Decrement on confirm; "Sold out" handling |
| F14 | Auto-pause on seller reply | Detect human replies from the Page inbox (message echoes) |
| F15 | Returning customers | "Use the same details as last time?" |
| F16 | Language toggle | English / Taglish copy sets |

### V2 (P2–P3)
| ID | Feature | Summary |
|---|---|---|
| F17 | Comment-to-order ("mine") | Live-selling automation: comment keyword → private reply → order flow |
| F18 | AI answers | Claude API answers free-text questions grounded in the FAQ tab (paid) |
| F19 | Multi-Page | One deployment serving several client Pages |
| F20 | Shipping zones | Metro Manila vs provincial rates |

---

## 5. Core workflows

### W1 — First contact
1. Customer taps **Get Started** or sends any message.
2. Bot replies with the greeting and quick replies: **🛍 Shop**, **❓ FAQ**, **📦 Track order**, **🙋 Talk to seller**.
3. The greeting includes a one-line privacy notice with a link.

### W2 — FAQ
1. Customer types "hm po" / "magkano" / "cod?".
2. Normalize text → match intent (section 10.4).
3. Reply with the FAQ answer (and a **Shop** quick reply when relevant).
4. No match → friendly fallback with quick replies. Two misses in a row → offer **Talk to seller**.

### W3 — Order (happy path)
1. **Shop** → carousel of active products (image, name, price, stock) with **Add to cart**.
2. **Add to cart** → quantity quick replies (1–5, "More") → item added.
3. Cart summary → **Add more** / **Checkout** / **Cancel**.
4. **Checkout** → delivery method (**Delivery** / **Pickup**).
5. Ask name → phone (validated PH mobile) → address (delivery only).
6. Payment method (**COD** / **GCash** / **Bank transfer**, per Settings).
7. Summary with **✅ Confirm** / **✏️ Edit** / **❌ Cancel**.
8. **Confirm** → re-check stock and prices → create order in DB (one transaction) → reply with order code and payment instructions → append to Orders tab → email seller.

**Failure/recovery:**
- Invalid phone → explain format ("09XXXXXXXXX") and ask again; 3 failures → offer Talk to seller.
- Product became inactive/out of stock at confirm → remove it, show updated cart.
- Sheet append fails → order is still saved in DB with `sheet_synced=false`; resync retries later. The customer is never told "error" for a sheet issue.
- Customer types something unexpected mid-flow → global commands work anytime (`menu`, `cancel`, `seller`, `track`); otherwise repeat the current question with quick replies.
- Idle > 24 h mid-flow → reset to IDLE, keep cart for 24 h.

### W4 — Talk to seller
Customer taps **Talk to seller** → bot says the seller will reply soon (with business hours) → conversation `paused_until = now + HANDOVER_PAUSE_HOURS` → seller gets an email with a link to the Page inbox. While paused, the bot stays silent except for the `menu` command, which resumes it.

### W5 — Track order
**Track order** → bot lists the customer's last 3 orders (by PSID only) with status from the Orders tab.

### W6 — Seller updates status (V1)
Seller changes Status in the Sheet → an Apps Script `onEdit` trigger calls `POST /admin/order-status` → if the customer's last message was within 24 hours, send an update; otherwise log "outside window". (Check Meta's current policy on message tags/utility messages before sending anything outside the window.)

---

## 6. Tech stack

| Area | Choice | Why | Alternatives considered |
|---|---|---|---|
| Language | Python 3.12 | Same stack as your other projects | Node.js + Express (equally good) |
| Web framework | FastAPI + Uvicorn | Async, typed, auto docs, tiny | Flask |
| HTTP client | httpx | Async Send API calls | requests |
| Config / models | pydantic-settings, pydantic v2 | Validated config and payloads | — |
| Database | PostgreSQL on Supabase (prod), SQLite (local) | Render free disk is wiped on restart, so prod needs a managed DB | Neon Postgres, Upstash Redis |
| ORM + migrations | SQLAlchemy 2.0 + Alembic | Same models for SQLite and Postgres | SQLModel, raw SQL |
| Postgres driver | psycopg 3 | Current standard | asyncpg |
| Sheets | gspread + service account | Seller-friendly admin | Airtable (seller must learn it) |
| Fuzzy matching | rapidfuzz | Handles typos like "magkno" | difflib (slower, weaker) |
| Retries | tenacity | Send API / Sheets retries | — |
| Email | smtplib (stdlib) + Gmail app password | No dependency | Resend free tier |
| Hosting | Render web service | Free tier for demos; ~$7/month paid tier for clients | Koyeb, Google Cloud Run |
| Local tunnel | cloudflared (`cloudflared tunnel --url`) | Free, no account | ngrok |
| Tests | pytest, respx, FastAPI TestClient | Mock Graph API | — |
| Quality | ruff | One tool | — |

**Why not ManyChat?** Many sellers already know ManyChat. Your edge is custom ordering logic, Sheets integration, and no per-contact platform fees. Offering ManyChat setup is a fine side gig, but TindaBot shows real coding skill.

---

## 7. Architecture

**Style:** modular monolith (one FastAPI app). Conversation logic is a pure state machine, separated from Messenger I/O, so it's easy to test.

```mermaid
flowchart LR
    C["Customer (Messenger app)"] --> META[("Meta platform")]
    META -->|"POST /webhook"| API["FastAPI app on Render"]
    API --> SIG["Verify X-Hub-Signature-256"]
    SIG --> PARSE["Parse events"]
    PARSE --> IDEM["Dedupe by message id"]
    IDEM --> ROUTER["Event router"]
    ROUTER --> NLU["Intent matcher (FAQ)"]
    ROUTER --> SM["Conversation state machine"]
    SM --> CAT["Catalog + settings cache"]
    CAT --> GS[("Google Sheet: Products, FAQ, Settings, Orders")]
    SM --> ORD["Order service"]
    ORD --> DB[("Postgres: conversations, orders")]
    ORD --> GS
    ORD --> MAIL["Email notifier"]
    MAIL --> SELLER["Seller inbox"]
    SM --> SEND["Messenger Send API client"]
    NLU --> SEND
    SEND --> META
    SHEETEDIT["Apps Script onEdit (V1)"] -->|"POST /admin/order-status"| API
```

**Request lifecycle:**
1. Meta POSTs an event. The app reads the **raw body**, verifies the HMAC signature, and returns `200 EVENT_RECEIVED` immediately.
2. Processing runs as a FastAPI background task: parse → skip if `mid` already processed → load conversation (row lock) → route → state machine returns a list of outgoing messages + side effects → side effects run (DB, Sheet, email) → messages sent via Send API.
3. The state machine is **pure**: `handle(state, context, event) -> (new_state, new_context, replies, actions)`. No I/O inside.

---

## 8. Repository structure

```
tindabot/
├── src/tindabot/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, route registration, lifespan
│   ├── config.py
│   ├── logging_setup.py         # JSON logs + PII masking
│   ├── api/
│   │   ├── webhook.py           # GET verify, POST events
│   │   ├── admin.py             # token-protected admin endpoints
│   │   └── health.py
│   ├── webhook/
│   │   ├── signature.py         # HMAC verification
│   │   └── parser.py            # Meta payload → internal Event models
│   ├── messenger/
│   │   ├── client.py            # Send API, typing indicator, retries
│   │   ├── builders.py          # text, quick replies, carousel, buttons
│   │   └── profile.py           # Get Started, greeting, persistent menu
│   ├── conversation/
│   │   ├── states.py            # State enum + context model
│   │   ├── machine.py           # pure transition function
│   │   ├── payloads.py          # postback payload constants/parsing
│   │   ├── nlu.py               # intent matching
│   │   └── handlers/
│   │       ├── shop.py
│   │       ├── cart.py
│   │       ├── checkout.py
│   │       ├── faq.py
│   │       ├── handover.py
│   │       └── track.py
│   ├── catalog/
│   │   └── sheets_catalog.py    # Products/FAQ/Settings with TTL cache
│   ├── orders/
│   │   ├── service.py           # create order, stock check, sheet sync
│   │   └── codes.py             # order code generator
│   ├── notify/
│   │   └── email.py
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repositories.py
│   └── copy/
│       └── messages.py          # ALL bot text in one place (en + taglish)
├── migrations/                  # Alembic
├── scripts/
│   ├── setup_messenger_profile.py
│   ├── seed_sheet.py            # creates tabs, headers, demo products
│   └── apps_script_onedit.js    # V1: paste into the Sheet's Apps Script
├── tests/
│   ├── fixtures/meta_events/    # sample webhook payloads
│   ├── conversations/           # YAML conversation scripts
│   ├── unit/
│   └── integration/
├── docs/
│   └── BLUEPRINT.md
├── render.yaml
├── .env.example
├── alembic.ini
├── pyproject.toml
├── uv.lock
├── README.md
└── CLAUDE.md
```

---

## 9. Data model

### Database (SQLAlchemy; Postgres in prod, SQLite locally)

**customers**
| Field | Type | Req | Notes |
|---|---|---|---|
| psid | TEXT | yes | PK, Page-scoped user ID from Meta |
| last_name_used, last_phone, last_address | TEXT | no | For returning-customer prefill (V1); PII |
| created_at, last_seen_at | TIMESTAMPTZ | yes | `last_seen_at` drives the 24-hour window check |

**conversations**
| Field | Type | Req | Notes |
|---|---|---|---|
| psid | TEXT | yes | PK, FK → customers (CASCADE) |
| state | TEXT | yes | See section 10.1 |
| context | JSON | yes | Cart, draft order, pagination cursor |
| fail_count | INTEGER | yes | Consecutive unrecognized inputs |
| paused_until | TIMESTAMPTZ | no | Handover pause |
| updated_at | TIMESTAMPTZ | yes | |

**orders**
| Field | Type | Req | Notes |
|---|---|---|---|
| id | BIGSERIAL | yes | PK (internal) |
| order_code | TEXT | yes | **UNIQUE**, `TB-YYMMDD-XXXX` (random base32; not guessable) |
| psid | TEXT | yes | FK → customers (RESTRICT) |
| customer_name, phone, address | TEXT | name/phone yes | PII |
| delivery_method | TEXT | yes | `delivery` / `pickup` |
| payment_method | TEXT | yes | `cod` / `gcash` / `bank` |
| status | TEXT | yes | `pending` / `confirmed` / `paid` / `shipped` / `delivered` / `cancelled` |
| subtotal_minor, shipping_minor, total_minor | INTEGER | yes | Centavos |
| notes | TEXT | no | |
| sheet_synced | BOOLEAN | yes | Default false |
| payment_proof_url | TEXT | no | V1 |
| created_at, updated_at | TIMESTAMPTZ | yes | |

**order_items**
`id PK, order_id FK → orders (CASCADE), sku TEXT, name TEXT, unit_price_minor INTEGER, qty INTEGER (1–99), line_total_minor INTEGER` — name and price are **snapshotted** at order time.

**processed_events**
`mid TEXT PK, received_at TIMESTAMPTZ` — idempotency; rows older than 7 days are deleted daily.

```mermaid
erDiagram
    CUSTOMERS ||--|| CONVERSATIONS : has
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    CUSTOMERS {
        text psid PK
        timestamptz last_seen_at
    }
    CONVERSATIONS {
        text psid PK
        text state
        json context
        timestamptz paused_until
    }
    ORDERS {
        bigint id PK
        text order_code UK
        text psid FK
        text status
        int total_minor
        bool sheet_synced
    }
    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        text sku
        int qty
        int line_total_minor
    }
```

**Indexes:** `orders(psid, created_at DESC)` for tracking; `orders(sheet_synced) WHERE sheet_synced = false` for resync; `processed_events(received_at)` for cleanup.

**Retention:** `ORDER_PII_RETENTION_DAYS` (default 365). A daily job anonymizes name/phone/address on older orders; totals stay for reporting.

### Google Sheet (seller's admin panel)

| Tab | Columns | Owner |
|---|---|---|
| **Products** | `sku, name, description, price, stock, image_url, category, active` | Seller edits |
| **FAQ** | `intent, keywords (comma-separated), answer, show_shop_button` | Seller edits |
| **Settings** | `key, value` — shop_name, greeting, shipping_fee, pickup_address, business_hours, gcash_name, gcash_number, bank_details, payment_methods, handover_hours, privacy_url | Seller edits |
| **Orders** | `order_code, created_at, status, customer_name, phone, address, delivery, payment, items, total, notes, psid` | Bot appends; seller edits `status`/`notes` |

---

## 10. Core logic specifications

### 10.1 Conversation state machine

| State | Expected input | Next state |
|---|---|---|
| IDLE | Any text → intent routing; `SHOP` → carousel | IDLE / BROWSING |
| BROWSING | `PRODUCT:<sku>` | CHOOSING_QTY |
| CHOOSING_QTY | `QTY:<n>` or a number 1–99 | CART_REVIEW |
| CART_REVIEW | `ADD_MORE` / `CHECKOUT` / `CANCEL` | BROWSING / ASK_DELIVERY / IDLE |
| ASK_DELIVERY | `DELIVERY:delivery` / `DELIVERY:pickup` | ASK_NAME |
| ASK_NAME | Text 2–80 chars | ASK_PHONE |
| ASK_PHONE | Valid PH mobile | ASK_ADDRESS (delivery) / ASK_PAYMENT (pickup) |
| ASK_ADDRESS | Text 10–300 chars | ASK_PAYMENT |
| ASK_PAYMENT | `PAY:cod` / `PAY:gcash` / `PAY:bank` | CONFIRMING |
| CONFIRMING | `CONFIRM` / `EDIT` / `CANCEL` | IDLE (order placed) / ASK_DELIVERY / IDLE |

**Global commands (any state):** `menu`, `cancel`, `track`, `seller`/`agent`/`tao`. They win over state-specific handling.

### 10.2 Postback / quick-reply payloads
`SHOP`, `SHOP_PAGE:<n>`, `PRODUCT:<sku>`, `QTY:<n>`, `ADD_MORE`, `CHECKOUT`, `DELIVERY:<method>`, `PAY:<method>`, `CONFIRM`, `EDIT`, `CANCEL`, `TRACK`, `FAQ`, `TALK_TO_SELLER`, `GET_STARTED`. Always validate payloads against the current catalog; never trust a price or SKU from a payload without looking it up.

### 10.3 Messenger limits to respect
- Text messages ≤ 2,000 characters (split long replies).
- Quick replies ≤ 13 per message.
- Generic template (carousel) ≤ 10 elements; each element ≤ 3 buttons; title/subtitle ≤ 80 chars.
- Button template ≤ 3 buttons.
- Standard messaging window: you can reply freely within 24 hours of the customer's last message.
- In development mode, only people with a role on your Meta app can chat with the bot. Going live for the public requires App Review for messaging permissions and usually Business Verification. Check Meta's current docs; requirements change.

### 10.4 Intent matching (FAQ)
1. Lowercase, strip emojis and punctuation, collapse repeated letters ("hmmm" → "hm").
2. Exact keyword match → intent.
3. Otherwise rapidfuzz `partial_ratio` ≥ 85 against keywords → best intent.
4. Ties → higher-priority intent (order in FAQ tab).

| Intent | Example keywords |
|---|---|
| price | hm, how much, magkano, presyo, price, pm price |
| availability | avail, available, meron pa, may stock, stock |
| shipping | sf, shipping, delivery, deliver, ship, magkano sf |
| cod | cod, cash on delivery, pwede cod |
| location | location, saan, where, address, pickup, meetup |
| hours | open, bukas, hours, anong oras |
| payment | gcash, bank, bpi, bdo, payment, bayad |
| human | seller, agent, tao, human, kausap, admin |

### 10.5 Validation rules
- **Phone:** strip spaces/dashes → `^(09\d{9}|\+639\d{9}|639\d{9})$` → store as `09XXXXXXXXX`.
- **Name:** 2–80 chars, letters/spaces/`.-'ñÑ`.
- **Address:** 10–300 chars.
- **Quantity:** 1–99 and ≤ stock.
- **Rate limit:** > 20 messages/minute from one PSID → ignore extras (in-memory counter).

### 10.6 Order confirmation message (example)
```
🧾 Order summary
2 × Ube Cheese Pandesal (₱180) = ₱360
1 × Choco Crinkles (₱120) = ₱120
Shipping: ₱80
Total: ₱560
Deliver to: Juan Dela Cruz · 0917 123 4567
123 Mabini St, Quezon City
Payment: GCash
```
After confirm: `Salamat! Your order code is TB-261001-7QK2.` + payment instructions from Settings.

### 10.7 Reliability rules
- Verify signature with `hmac.compare_digest` on the **raw** request body using the App Secret.
- Return 200 fast; Meta retries failed deliveries and may disable a webhook that keeps failing.
- Idempotency: insert `mid` into `processed_events` first; on conflict, skip.
- Per-customer serialization: lock the conversation row (`SELECT … FOR UPDATE` in Postgres) while handling an event.
- Send API: retry 3× on 5xx/timeouts; don't retry 4xx (log them).
- Order creation and item insert in **one DB transaction**; Sheet + email after commit; failures leave `sheet_synced=false` for `POST /admin/resync`.
- Catalog/FAQ/Settings cached in memory for `CATALOG_CACHE_SECONDS` (300); `POST /admin/reload` refreshes immediately.

### 10.8 API endpoints

| Method | Route | Auth | Purpose | Responses |
|---|---|---|---|---|
| GET | `/webhook` | Verify token | Meta subscription check: if `hub.mode=subscribe` and `hub.verify_token` matches, return `hub.challenge` as plain text | 200 / 403 |
| POST | `/webhook` | Signature | Receive events | 200 always after valid signature; 403 invalid signature |
| GET | `/healthz` | None | Liveness (no DB call) | 200 `{"status":"ok"}` |
| GET | `/readyz` | None | DB + Sheet reachable | 200 / 503 |
| POST | `/admin/reload` | Bearer `ADMIN_TOKEN` | Clear caches | 200 / 401 |
| POST | `/admin/resync` | Bearer | Re-send unsynced orders to Sheet | 200 `{"synced": n}` |
| POST | `/admin/pause/{psid}` / `/admin/resume/{psid}` | Bearer | Handover control | 200 / 404 |
| POST | `/admin/order-status` | Bearer | V1: notify customer of status change `{order_code, status}` | 200 `{"sent": bool, "reason": str}` |

**Admin response format:** `{"success": true, "data": {...}}` or `{"success": false, "error": {"code": "...", "message": "..."}}`.

---

## 11. Configuration (`.env.example`)

```bash
APP_ENV=development                 # development | production
LOG_LEVEL=INFO

# --- Meta (from your Meta app dashboard) ---
META_APP_SECRET=
META_VERIFY_TOKEN=                  # any long random string you choose
META_PAGE_ACCESS_TOKEN=
META_PAGE_ID=
META_GRAPH_VERSION=                 # pin the current version shown in your app dashboard, e.g. vXX.0

# --- Database ---
DATABASE_URL=sqlite:///data/tindabot.db
# production: postgresql+psycopg://USER:PASSWORD@HOST:PORT/postgres  (Supabase pooler string)

# --- Google Sheets ---
GOOGLE_SERVICE_ACCOUNT_JSON_B64=    # base64 of the service-account JSON (easier on hosting)
GOOGLE_SHEET_ID=

# --- Seller notifications ---
SELLER_NOTIFY_EMAIL=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_APP_PASSWORD=

# --- Behavior ---
ADMIN_TOKEN=                        # long random string
HANDOVER_PAUSE_HOURS=12
CATALOG_CACHE_SECONDS=300
ORDER_PII_RETENTION_DAYS=365
MAX_MESSAGES_PER_MINUTE=20

# --- V1 ---
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_BUCKET=payment-proofs
```
**Environments:** development uses SQLite + your test Page + a tunnel; production uses Supabase Postgres + the client's Page + Render. Never reuse tokens across environments.

---

## 12. Error handling and logging

| Situation | Customer sees | System does |
|---|---|---|
| Unknown message | Friendly fallback + quick replies | `fail_count += 1`; 2 in a row → offer seller |
| Invalid input in a step | What's wrong + example | Stay in state |
| Sheet read fails | Cached catalog used; if no cache: "Our shop list is loading, try again in a minute" + Talk to seller | Log error, retry next request |
| Sheet write fails | Nothing (order is safe) | `sheet_synced=false`, resync later |
| Email fails | Nothing | Logged; included in resync |
| Send API 4xx | — | Logged with Meta error code; no retry |
| Token invalid (error code 190) | — | Critical log + email operator |
| Unhandled exception | "Sorry, something went wrong. A person will follow up." | Pause bot for that PSID 1 h, log traceback |

**Structured JSON logs:** event type, PSID hash (not raw), state transition, duration, Meta error codes.
**Never log:** tokens, app secret, full phone numbers (mask `0917***4567`), addresses, names.

---

## 13. Security and privacy

- **Webhook authenticity:** reject any POST without a valid `X-Hub-Signature-256`.
- **Admin endpoints:** bearer token, constant-time comparison, HTTPS only (Render provides TLS).
- **IDOR prevention:** tracking queries always filter by the sender's PSID; order codes are random, not sequential.
- **Input handling:** strict length limits; treat all text as data; never evaluate or follow customer-sent URLs.
- **Attachments (V1):** download only from Meta CDN hosts, image content types only, ≤ 10 MB; store in a private bucket with signed URLs (prevents SSRF and public exposure of receipts).
- **Secrets:** env vars only; `.env` gitignored; rotate the Page token if leaked.
- **Privacy (RA 10173):** you collect names, phone numbers, and addresses. Show a short privacy notice in the greeting, use data only for orders, limit Sheet sharing to the seller's team, and anonymize after the retention period. The seller is the data controller; you act as their processor, so put this in your service agreement.
- **Dependencies:** pinned in `uv.lock`; monthly update + tests.

---

## 14. Testing strategy

| Layer | What | Tools |
|---|---|---|
| Unit | signature verification, payload parser, NLU, validators, order codes, message builders (limits) | pytest |
| State machine | Table-driven transition tests; pure function, no mocks needed | pytest |
| Conversation scripts | YAML scripts replayed through the full router with fakes | pytest |
| Integration | `TestClient` POSTs signed fixture payloads → DB rows + mocked Send API calls | pytest, respx |
| Manual | Real chat on your test Page via tunnel | Checklist in README |

**Conversation script example (`tests/conversations/happy_path_cod.yaml`):**
```yaml
name: happy path, delivery, COD
steps:
  - send: "hi"
    expect_state: IDLE
    expect_reply_contains: "Welcome"
  - postback: SHOP
    expect_state: BROWSING
  - postback: "PRODUCT:UBE-01"
    expect_state: CHOOSING_QTY
  - quick_reply: "QTY:2"
    expect_state: CART_REVIEW
  - postback: CHECKOUT
    expect_state: ASK_DELIVERY
  - quick_reply: "DELIVERY:delivery"
  - send: "Juan Dela Cruz"
  - send: "0917 123 4567"
    expect_state: ASK_ADDRESS
  - send: "123 Mabini St, Quezon City"
  - quick_reply: "PAY:cod"
    expect_state: CONFIRMING
  - postback: CONFIRM
    expect_state: IDLE
    expect_order_created: true
```
**Other must-have scripts:** invalid phone ×3 → seller offer; "cancel" mid-checkout; out-of-stock at confirm; duplicate `mid` delivered twice → one order; paused conversation stays silent; tracking shows only own orders.

---

## 15. Setup, running, and deployment

### Meta setup (development)
1. Create a Facebook Page for demos (e.g., "Kape't Tinapay Demo").
2. developers.facebook.com → create an app (Business type) → add **Messenger**.
3. Connect your Page and generate a **Page access token**.
4. Start the app locally, then run `cloudflared tunnel --url http://localhost:8000`.
5. Set the webhook callback URL to `https://<tunnel>/webhook` with your `META_VERIFY_TOKEN`; subscribe the Page to `messages` and `messaging_postbacks` (plus `message_echoes` in V1).
6. Run `uv run python scripts/setup_messenger_profile.py` (Get Started, greeting, persistent menu).
7. Message your Page from your own account.

### Local
```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python scripts/seed_sheet.py
uv run uvicorn tindabot.main:app --reload --port 8000
```

### Production (Render + Supabase)
- Supabase: create a project → copy the **pooler** connection string into `DATABASE_URL`.
- Render: web service from GitHub; build `pip install uv && uv sync --frozen`; start `uv run alembic upgrade head && uv run uvicorn tindabot.main:app --host 0.0.0.0 --port $PORT`; health check `/healthz`; env vars from section 11. (Verify commands against Render's current docs.)
- Update the Meta webhook URL to the Render URL.
- **Free-tier caveats:** Render's free web service sleeps when idle, so the first reply after a quiet period can take up to about a minute; fine for demos, not for clients. Supabase free projects pause after about a week of inactivity. For paying clients, use a paid instance and include hosting in your monthly fee.

### Deployment diagram
```mermaid
flowchart LR
    GH["GitHub repo"] -->|"auto deploy on push to main"| R["Render web service"]
    R --> SB[("Supabase Postgres")]
    R --> GSH[("Google Sheets API")]
    R --> SMTP["Gmail SMTP"]
    META[("Meta webhooks + Send API")] <--> R
```

---

## 16. Costs

| Stage | Cost |
|---|---|
| Development + demo | $0 (Render free, Supabase free, Sheets, cloudflared, Gmail SMTP) |
| One paying client | Render paid instance (around $7/month at time of writing) + Supabase free tier; charge this in your monthly fee |
| Growing (5+ clients, V2 multi-Page) | One paid instance + Supabase Pro if needed; check current pricing |

---

## 17. Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| App Review / Business Verification delays for going live | High | High | Demo in dev mode; start review early for the first client; budget 1–3 weeks |
| Meta API/policy changes | Medium | Medium | Pin Graph version; review changelog quarterly |
| Free-tier cold starts | High (free) | Medium | Paid instance for clients |
| Unpredictable Taglish input | High | Low | Quick replies everywhere; fuzzy matching; fast handover |
| Duplicate orders from retries | Medium | High | `mid` idempotency; confirm-step lock |
| Sheet quota/outage | Low | Medium | Cache + DB as source of truth + resync |
| PII leak | Low | High | Masked logs, limited sharing, retention job |
| Token expiry | Medium | High | Long-lived/system-user token; alert on error 190 |

---

## 18. Implementation roadmap

Estimated time: **Phases 0–8 ≈ 5–7 days**, **Phases 9–10 ≈ 1–2 days**.

### Phase 0 — Setup
- [ ] 0.1 (P0) uv project, FastAPI skeleton, `/healthz`, ruff, pytest
- [ ] 0.2 (P0) `config.py` + `.env.example`
- [ ] 0.3 (P0) JSON logging with PII masking helpers + tests
- [ ] 0.4 (P0) `CLAUDE.md`, README, `.gitignore`

### Phase 1 — Webhook foundation *(milestone: echo bot)*
- [ ] 1.1 (P0) GET `/webhook` verification + tests
- [ ] 1.2 (P0) Signature verification on raw body + tests
- [ ] 1.3 (P0) Payload parser → `Event` models (text, quick reply, postback, attachment) with fixture tests
- [ ] 1.4 (P0) Send API client (text, typing indicator, retries)
- [ ] 1.5 (P0) Echo reply via background task; test through cloudflared with your Page

### Phase 2 — Database
- [ ] 2.1 (P0) SQLAlchemy models + Alembic initial migration
- [ ] 2.2 (P0) Repositories: customers, conversations (with lock), orders, processed_events
- [ ] 2.3 (P0) Idempotency on `mid` + test

### Phase 3 — Sheets layer *(parallel with Phase 2)*
- [ ] 3.1 (P0) `seed_sheet.py` (tabs, headers, demo products, FAQ, settings)
- [ ] 3.2 (P0) Catalog/FAQ/Settings reader with TTL cache
- [ ] 3.3 (P0) Orders tab appender

### Phase 4 — Messages and profile
- [ ] 4.1 (P0) `copy/messages.py` with all bot text
- [ ] 4.2 (P0) Builders: quick replies, carousel, button template (enforce limits) + tests
- [ ] 4.3 (P0) `setup_messenger_profile.py`

### Phase 5 — FAQ and NLU
- [ ] 5.1 (P0) Text normalizer + intent matcher + tests with Taglish examples
- [ ] 5.2 (P0) FAQ handler + fallback + fail counter

### Phase 6 — Ordering state machine *(depends on 2–5)*
- [ ] 6.1 (P0) States, context model, payload constants
- [ ] 6.2 (P0) Shop + pagination
- [ ] 6.3 (P0) Cart (qty, add more, cancel)
- [ ] 6.4 (P0) Checkout steps with validators
- [ ] 6.5 (P0) Confirmation + global commands
- [ ] 6.6 (P0) Conversation script test runner + 6 scripts

### Phase 7 — Orders, notifications, handover, tracking
- [ ] 7.1 (P0) Order service: stock/price re-check, transaction, order code
- [ ] 7.2 (P0) Sheet sync + `sheet_synced` + `/admin/resync`
- [ ] 7.3 (P0) Seller email
- [ ] 7.4 (P0) Handover pause/resume + admin endpoints
- [ ] 7.5 (P0) Track order (own PSID only) + IDOR test
- [ ] 7.6 (P1) Retention/anonymization job + `processed_events` cleanup

### Phase 8 — Deploy
- [ ] 8.1 (P0) `render.yaml`, Supabase connection, migrations on start
- [ ] 8.2 (P0) Point Meta webhook to Render; full manual test checklist
- [ ] 8.3 (P1) Operator alert email on token error 190

### Phase 9 — Portfolio packaging
- [ ] 9.1 (P0) README: features, architecture diagram, setup, screenshots
- [ ] 9.2 (P0) Record demo (section 21)
- [ ] 9.3 (P0) Push to GitHub (no tokens, demo data only)

### Phase 10 — V1
- [ ] 10.1 (P1) Payment proof upload
- [ ] 10.2 (P1) Status notifications via Apps Script `onEdit`
- [ ] 10.3 (P1) Stock decrement + sold-out handling
- [ ] 10.4 (P1) Auto-pause on seller echo
- [ ] 10.5 (P2) Returning-customer prefill
- [ ] 10.6 (P2) Language toggle

### Phase 11 — V2 *(when a client pays for it)*
- [ ] 11.1 (P3) Comment-to-order ("mine") for live selling
- [ ] 11.2 (P3) AI answers grounded in FAQ
- [ ] 11.3 (P3) Multi-Page support

**Dependency summary:** Phase 1 blocks all Messenger work. Phases 2 and 3 run in parallel. Phase 6 needs 2–5. Phase 8 needs 7.

---

## 19. Definition of done (MVP)

- [ ] Invalid signatures are rejected; verification handshake works
- [ ] A new customer can complete an order in under 2 minutes using only taps + typing name/phone/address
- [ ] Order appears in DB and Sheet; seller receives an email
- [ ] Duplicate webhook deliveries create exactly one order
- [ ] "Talk to seller" pauses the bot; `menu` resumes it
- [ ] Customers can only track their own orders (tested)
- [ ] Top 8 FAQ intents answered correctly for Taglish test phrases
- [ ] Logs contain no tokens or unmasked PII
- [ ] Deployed on Render + Supabase and working with the test Page
- [ ] All conversation scripts and tests pass

---

## 20. CLAUDE.md starter

```markdown
# TindaBot
FastAPI Messenger bot: FAQ replies, product carousel, guided ordering, orders to Postgres + Google Sheets.
Full spec: docs/BLUEPRINT.md. Read the relevant section before changing code.

## Commands
- Install: `uv sync`
- Migrate: `uv run alembic upgrade head`
- Run: `uv run uvicorn tindabot.main:app --reload --port 8000`
- Test: `uv run pytest -q`
- Lint/format: `uv run ruff check . --fix && uv run ruff format .`

## Rules
- Work only on the task I name. Stop and summarize when done.
- conversation/machine.py stays pure: no DB, HTTP, or Sheets calls inside it.
- All customer-facing text lives in copy/messages.py.
- Never skip signature verification, idempotency, or PSID ownership checks.
- Never log tokens, secrets, or unmasked phone/address/name.
- Respect Messenger limits (section 10.3) in builders; add tests when changing them.
- Every behavior change gets a unit test or a conversation script.
- Don't add dependencies without asking.
```

---

## 21. Demo script (90 seconds, phone screen recording)

1. **0–10 s:** "Sellers answer 'hm po?' 100 times a day."
2. **10–25 s:** Type "hm po" → instant price reply with **Shop** button. Type "cod?" → COD answer.
3. **25–60 s:** Shop → carousel → add 2 items → checkout → name, phone, address → GCash → confirm → order code.
4. **60–75 s:** Cut to the Google Sheet: new row appears. Show the seller email.
5. **75–90 s:** Seller sets Status to "Shipped"; customer types "track" → "Shipped". End card: "Live-selling 'mine' automation and payment proof upload available."

---

## 22. Selling it

- **Who (PH):** Facebook sellers (clothing, food, pre-loved, beauty, pasalubong), home bakers, small restaurants taking pre-orders, social media managers handling multiple Pages. Find them in local seller Facebook groups and marketplaces.
- **Who (international):** Upwork jobs for "Messenger chatbot", "Facebook bot", "Meta Graph API", "WhatsApp/Messenger automation".
- **Gig title:** "I will build a Facebook Messenger order bot that saves orders to Google Sheets."
- **Starter pricing:**
  - PH sellers: ₱3,000–8,000 setup + ₱500–1,500/month (hosting + support)
  - International: $150–400 setup + $20–50/month
- **What to say about Meta's built-in auto-replies:** they handle simple FAQs; TindaBot adds full ordering, cart, order tracking, and a Sheet of every order.
- **Upsells:** "mine" comment automation for live sellers, payment proof tracking, AI answers, multi-Page for agencies.
- **Honesty rule:** tell clients that going live for the public requires Meta's review and that you'll handle the submission, but approval timing is up to Meta.
