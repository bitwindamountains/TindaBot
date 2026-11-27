# TindaBot

[![CI](https://github.com/bitwindamountains/TindaBot/actions/workflows/ci.yml/badge.svg)](https://github.com/bitwindamountains/TindaBot/actions/workflows/ci.yml)

A Facebook Messenger ordering assistant for small Philippine online shops. Customers browse products, ask questions in English or Taglish, check out and track orders in chat. The seller runs the shop from a web workspace backed by PostgreSQL and Google Sheets.

**[Try the live demo →](https://tindabot.onrender.com)** A sample shop ("Sari Studio") opens in preview mode. On the **Automation** page, **Talk to your bot** chats with the real conversation logic. Nothing is saved or sent. It runs on free hosting, so the first load can take up to a minute.

![Seller workspace overview with orders, revenue and stock](docs/images/workspace.webp)


> **Status:** demo only, not yet in use. The code is complete and tested locally; connecting a real Facebook Page, a supervised pilot and monitoring are still to do. See [release status](docs/RELEASE_STATUS.md).

## Features

**For customers (in Messenger)**
- Browse products, add quantities ("2 ube pandesal po"), and choose delivery or pickup
- Pay by cash on delivery, GCash or bank transfer, using instructions the seller configures
- Ask questions mid-checkout: the bot answers from the FAQ, then repeats the current step
- Track orders, and opt in to updates when an order is confirmed, shipped or delivered
- Type `MENU` to return to the bot after talking to the seller

**For the seller (web workspace)**
- Order overview and detail, status changes, private notes, refund tracking, CSV export
- Inventory with stock adjustments; the product catalog and FAQ are edited in Google Sheets
- **Automation page:** how many conversations the bot handled alone, the questions it couldn't answer (each with an **Add to FAQ** row ready to paste), and a test chat
- Human takeover: when the seller replies from the Page inbox, the bot pauses for that customer
- Light and dark themes, keyboard shortcuts (`Ctrl/Cmd+K`, `/`), mobile layout, reduced-motion support

**No AI.** Understanding is deterministic: phrase and keyword matching in English and Taglish, so answers are predictable and never invented.

## Walkthrough: a seller's day

**1. Work the order queue.** Every order by stage, from to-confirm to delivered, with filters and CSV export.

![Orders page with order counts by stage and the orders table](docs/images/orders.webp)

**2. Confirm an order.** The order panel shows the items, delivery and payment method, and moves the order through each stage.

![Order side panel with total, status steps, customer and items](docs/images/order-detail.webp)

**3. Keep stock honest.** The catalog shows what is in stock or running low. Every stock adjustment is logged.

![Inventory cards with prices, stock counts and adjust-stock buttons](docs/images/inventory.webp)

**4. Teach the bot.** How many conversations the bot handled alone, and each question it missed, ready to add to the FAQ.

![Automation page: 44 of 52 conversations handled, with missed Taglish questions](docs/images/automation.webp)

**5. Jump anywhere.** Quick actions (`Ctrl/Cmd+K`) open any page or task from the keyboard.

![Quick actions dialog](docs/images/quick-actions.webp)

## Engineering highlights

- **No lost or duplicate orders:** webhook events are signature-checked and stored before Messenger gets its acknowledgement. Duplicate events are ignored, and each checkout creates at most one order (enforced in PostgreSQL).
- **Correct stock under concurrency:** orders and inventory are allocated in one transaction. A price change since the quote asks the customer to reconfirm.
- **Reliable outbound messages:** a separate worker sends Messenger replies, emails and Sheet updates through a transactional outbox, with retries per destination. Results that can't be confirmed go to the seller for review instead of being retried blindly.
- **Safe by default:** the default `dry_run` mode sends nothing. Production startup refuses SQLite, weak or shared admin tokens, and missing settings.
- **Privacy:** customers' personal fields can be erased on request; staff tokens can be limited to order status without customer data.
- **Tested:** 194 Python tests in CI (87% coverage, including PostgreSQL concurrency and migration tests) and 36 browser tests for the workspace. A local load test handled 6,000 webhook events in 10 minutes with no errors and a 32 ms p95 acknowledgement ([report](docs/validation/local-load.json)).

## Tech stack

| Part | Technology |
| --- | --- |
| Service | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite for local demos) |
| Integrations | Messenger Platform (Graph API), Google Sheets (gspread), SMTP |
| Workspace | Plain HTML, CSS and JavaScript; a small React + ShaderGradient hero bundle |
| Quality | pytest, Ruff, pip-audit, Playwright, GitHub Actions |

## Run it locally

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen
cp .env.example .env              # then fill in local settings
uv run tindabot new-token         # generate the admin and status tokens for .env
uv run alembic upgrade head
uv run tindabot seed-demo
uv run uvicorn tindabot.main:create_app --factory --port 8000 --no-access-log
uv run tindabot worker            # in a second terminal
```

Open **http://127.0.0.1:8000/** for the workspace. Choose **Connect shop** and enter your `ADMIN_TOKEN` to see the real database instead of the sample data. API docs are at `/docs` in development.

To run a complete simulated order without any Facebook or Google credentials:

```sh
uv run python scripts/demo_order.py
```

SQLite is fine for local demos. For concurrency testing, start PostgreSQL with `docker compose up -d postgres` and set `DATABASE_URL=postgresql+psycopg://tindabot:local-development-only@127.0.0.1:5432/tindabot` before migrating. That password is for local development only.

## Tests

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pip-audit --skip-editable
npm ci && npx playwright install chromium && npm run test:ui     # browser tests
```

PostgreSQL tests run only when `TEST_DATABASE_URL` points to a disposable database whose name ends in `_test`, because they truncate tables. CI starts its own PostgreSQL and runs them.

## Connecting a real Page

1. Create a Meta app and test Page, and put the app secret, verification token, Page token and app ID in `.env`.
2. Expose the API over HTTPS, register `/webhook`, and subscribe the Page to messaging events.
3. Share one Google Sheet with a service account and run `uv run tindabot setup-sheet` to create the **Products**, **FAQ**, **Orders** and **Commands** tabs.
4. Configure SMTP for seller emails, run `uv run tindabot setup-profile`, then set `DELIVERY_MODE=live`.

### How the seller uses the Sheet

| Tab | Seller edits | Behavior |
| --- | --- | --- |
| Products | `sku, name, price, stock, active, image_url` | Price in pesos. `stock` sets the starting stock for **new** SKUs only, so re-importing never refills sold stock. |
| FAQ | `keywords, answer` | Comma-separated words or phrases, matched in order. |
| Orders | nothing | Written by the worker and protected. The database stays the source of truth. |
| Commands | `command_id, order_id, expected_version, action` | Change an order's status (`confirmed`, `paid`, `shipped`, `delivered`, `cancelled`) or `pause`/`resume` the bot. The worker writes the result. |

Commands are checked every minute. A reused command ID can't apply twice, and a wrong version is rejected visibly. To add stock, use **Inventory → Adjust stock** in the workspace. Day-to-day procedures are in the [operations runbook](docs/OPERATIONS.md).

## Documentation

- [Deployment](docs/DEPLOYMENT.md): Render Blueprint, database and secrets
- [Operations runbook](docs/OPERATIONS.md): daily use, Sheet tabs, recovery
- [Release status](docs/RELEASE_STATUS.md) and [production plan](docs/PRODUCTION_PLAN.md): what's left before real orders
- [Design system](docs/DESIGN_SYSTEM.md): tokens, motion and UI rules
- [Order journal](docs/ORDER_JOURNAL.md), [delivery recovery](docs/DELIVERY_RECOVERY.md), [handover queue](docs/HANDOVER_QUEUE.md)
- [Development notes](docs/dev-notes/): the original blueprint, progress log and past reviews

## Known limits

- One Facebook Page and one worker per deployment
- Messages, emails and Sheet writes can't share the database transaction, so an unconfirmed send needs the seller to check it
- Order updates go out only within Messenger's 24-hour window after the customer's last message
- Not included: payment screenshots, broadcasts, courier integrations, AI answers
