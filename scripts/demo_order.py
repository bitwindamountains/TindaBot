"""Run a real application transaction flow in an isolated temporary SQLite database."""

import tempfile
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from tindabot.catalog import CatalogImport, import_catalog
from tindabot.cli import DEMO
from tindabot.config import Settings
from tindabot.db import Base, Conversation, Database, Order, Product
from tindabot.events import accept_events
from tindabot.service import process_one


def main():
    with tempfile.TemporaryDirectory(prefix="tindabot-demo-") as directory:
        settings = Settings(
            _env_file=None,
            app_env="test",
            delivery_mode="dry_run",
            meta_page_id="100",
            database_url=f"sqlite:///{Path(directory) / 'demo.db'}",
            max_messages_per_minute=1000,
        )
        db = Database(settings)
        Base.metadata.create_all(db.engine)
        try:
            with db.sessions.begin() as session:
                import_catalog(session, CatalogImport(**DEMO))

            def send(value):
                accept_events(
                    db,
                    settings,
                    {
                        "object": "page",
                        "entry": [
                            {
                                "id": "100",
                                "messaging": [
                                    {
                                        "sender": {"id": "200"},
                                        "recipient": {"id": "100"},
                                        "timestamp": int(time.time() * 1000),
                                        "message": {"mid": str(uuid.uuid4()), "text": value},
                                    }
                                ],
                            }
                        ],
                    },
                )
                process_one(db, settings)

            for value in [
                "SHOP",
                "PRODUCT:UBE-01",
                "QTY:2",
                "CHECKOUT",
                "DELIVERY:delivery",
                "Demo Customer",
                "09171234567",
                "123 Demo Street, Quezon City",
                "PAY:cod",
            ]:
                send(value)
            with db.sessions() as session:
                context = session.get(Conversation, "100:200").context
            token = f"CONFIRM:{context['checkout_id']}:{context['version']}"
            send(token)
            send(token)
            with db.sessions() as session:
                orders = session.scalars(select(Order)).all()
                assert len(orders) == 1
                assert orders[0].total_minor == 44000
                assert session.get(Product, "UBE-01").stock == 23
                print(f"PASS: {orders[0].code}, PHP 440.00, one order after two confirmations.")
                print(
                    "Inventory allocated atomically. Sheet/email jobs queued. No external messages sent."
                )
        finally:
            db.engine.dispose()


if __name__ == "__main__":
    main()
