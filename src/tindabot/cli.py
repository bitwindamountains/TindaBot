import argparse
import json
import secrets
import sys

from sqlalchemy import select

from tindabot.catalog import CatalogImport, import_catalog
from tindabot.config import Settings
from tindabot.db import Database, Inbox, Outbox, Record
from tindabot.integrations import COMMAND_HEADERS, ORDER_HEADERS, Integrations

DEMO = {
    "products": [
        {"sku": "UBE-01", "name": "Ube Cheese Pandesal", "price_minor": 18000, "stock": 25},
        {"sku": "CHOCO-01", "name": "Choco Crinkles", "price_minor": 12000, "stock": 25},
    ],
    "faq": [
        {"keywords": "hm,magkano,price,how much", "answer": "Tap Shop to see current prices."},
        {
            "keywords": "cod,cash on delivery",
            "answer": "Choose your available payment method at checkout.",
        },
        {
            "keywords": "shipping,sf,delivery",
            "answer": "Your delivery fee is shown before you confirm.",
        },
        {
            "keywords": "gcash,bank,payment,bayad",
            "answer": "Payment options are shown at checkout. The seller verifies payments.",
        },
        {
            "keywords": "avail,available,stock,meron",
            "answer": "Tap Shop to see the available products.",
        },
        {
            "keywords": "location,saan,pickup",
            "answer": "Choose pickup at checkout or ask the seller for directions.",
        },
        {
            "keywords": "hours,open,bukas",
            "answer": "Orders can be submitted any time. Ask the seller about opening hours.",
        },
    ],
}


def main():
    parser = argparse.ArgumentParser(description="TindaBot operator tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-demo", help="Import demo data into non-production DB")
    sub.add_parser("worker")
    sub.add_parser("doctor", help="Report configuration presence without revealing secrets")
    sub.add_parser("jobs", help="List failed/uncertain work without customer payloads")
    replay = sub.add_parser(
        "retry-event", help="Retry quarantined inbox event after fixing its cause"
    )
    replay.add_argument("event_id", type=int)
    sub.add_parser(
        "setup-sheet", help="Create missing Sheet tabs; does not overwrite existing tabs"
    )
    sub.add_parser("setup-profile", help="Configure the test/production Page Messenger profile")
    sub.add_parser("new-token", help="Print a new token for secure local configuration")
    args = parser.parse_args()
    if args.command == "new-token":
        print(secrets.token_urlsafe(48))
        return
    settings = Settings()
    if args.command == "doctor":
        required = [
            "meta_page_id",
            "meta_app_id",
            "meta_graph_version",
            "meta_app_secret",
            "meta_verify_token",
            "meta_page_access_token",
            "admin_token",
            "status_token",
            "google_sheet_id",
            "google_service_account_json_b64",
            "seller_notify_email",
            "smtp_host",
            "smtp_user",
            "smtp_password",
            "smtp_from",
            "privacy_url",
        ]
        missing = [
            key.upper()
            for key in required
            if not (
                getattr(settings, key).get_secret_value()
                if hasattr(getattr(settings, key), "get_secret_value")
                else getattr(settings, key)
            )
        ]
        print(
            json.dumps(
                {
                    "environment": settings.app_env,
                    "delivery_mode": settings.delivery_mode,
                    "missing": missing,
                    "production_acknowledged": settings.production_acknowledged,
                },
                indent=2,
            )
        )
        sys.exit(1 if missing else 0)
    if args.command == "worker":
        from tindabot.worker import run

        run()
        return
    db = Database(settings)
    try:
        if args.command == "seed-demo":
            if settings.app_env == "production":
                parser.error("Demo data is forbidden in production")
            with db.sessions.begin() as session:
                import_catalog(session, CatalogImport(**DEMO))
            print("Demo catalog imported. Existing inventory was preserved.")
        elif args.command == "jobs":
            with db.sessions() as session:
                for model in (Inbox, Outbox):
                    for job in session.scalars(
                        select(model).where(model.status.in_(["failed", "uncertain"]))
                    ):
                        print(
                            json.dumps(
                                {
                                    "queue": model.__tablename__,
                                    "id": job.id,
                                    "status": job.status,
                                    "error": job.error,
                                    "attempts": job.attempts,
                                }
                            )
                        )
        elif args.command == "retry-event":
            with db.sessions.begin() as session:
                event = session.scalar(
                    select(Inbox).where(Inbox.id == args.event_id).with_for_update()
                )
                if not event or event.status != "failed":
                    parser.error("Event is not quarantined")
                event.status, event.attempts, event.next_attempt, event.error = (
                    "pending",
                    0,
                    0,
                    None,
                )
                session.add(
                    Record(key=f"retry:{secrets.token_hex(16)}", value={"event_id": event.id})
                )
            print("Event queued for retry.")
        elif args.command == "setup-sheet":
            integrations = Integrations(settings)
            try:
                sheet = integrations.sheet()
                existing = {w.title for w in sheet.worksheets()}
                tabs = {
                    "Products": ["sku", "name", "price", "stock", "active", "image_url"],
                    "FAQ": ["keywords", "answer"],
                    "Orders": ORDER_HEADERS,
                    "Commands": COMMAND_HEADERS,
                }
                for name, headers in tabs.items():
                    if name not in existing:
                        worksheet = sheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                        worksheet.append_row(headers, value_input_option="RAW")
                print(
                    "Sheet tabs ready. Protect Orders columns and Commands results before launch."
                )
            finally:
                integrations.close()
        elif args.command == "setup-profile":
            integrations = Integrations(settings)
            try:
                response = integrations.http.post(
                    f"https://graph.facebook.com/{settings.meta_graph_version}/{settings.meta_page_id}/messenger_profile",
                    headers={
                        "Authorization": f"Bearer {settings.meta_page_access_token.get_secret_value()}"
                    },
                    json={
                        "get_started": {"payload": "GET_STARTED"},
                        "greeting": [
                            {"locale": "default", "text": f"Welcome to {settings.shop_name}"}
                        ],
                        "persistent_menu": [
                            {
                                "locale": "default",
                                "composer_input_disabled": False,
                                "call_to_actions": [
                                    {"type": "postback", "title": "Shop", "payload": "SHOP"},
                                    {
                                        "type": "postback",
                                        "title": "Track order",
                                        "payload": "TRACK",
                                    },
                                    {
                                        "type": "postback",
                                        "title": "Talk to seller",
                                        "payload": "SELLER",
                                    },
                                ],
                            }
                        ],
                    },
                )
                print(
                    "Profile configured."
                    if response.is_success
                    else f"Profile rejected: HTTP {response.status_code}"
                )
                if not response.is_success:
                    sys.exit(1)
            finally:
                integrations.close()
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
