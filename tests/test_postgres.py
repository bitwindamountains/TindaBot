import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from conftest import checkout, envelope
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from tindabot.catalog import CatalogImport, import_catalog
from tindabot.cli import DEMO
from tindabot.db import Conversation, Database, Inbox, Order, Outbox, Product
from tindabot.events import accept_events
from tindabot.main import create_app
from tindabot.service import process_one
from tindabot.worker import claim_job

pytestmark = pytest.mark.postgres


def test_workspace_groups_afternoon_orders_into_the_correct_manila_day(pgdb, settings):
    confirmation = checkout(pgdb, settings)
    accept_events(pgdb, settings, envelope(confirmation))
    assert process_one(pgdb, settings)
    yesterday = int((time.time() + 28800) // 86400) * 86400 - 28800 - 86400
    with pgdb.sessions.begin() as session:
        order = session.scalar(select(Order))
        order.created_at = yesterday + 22 * 3600
        total = order.total_minor
    with TestClient(create_app(settings, pgdb)) as client:
        data = client.get(
            "/admin/workspace", headers={"Authorization": "Bearer " + "a" * 40}
        ).json()
    assert data["series"][-2] == {"timestamp": yesterday, "value": total}
    assert data["series"][-1]["value"] == 0
    assert sum(point["value"] for point in data["series"]) == data["summary"]["order_value"]


@pytest.fixture
def pgdb(settings, monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
        pytest.fail("Refusing destructive test setup: use a dedicated database ending in _test")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "test")
    from pydantic import SecretStr

    settings.database_url = SecretStr(url)
    command.upgrade(Config("alembic.ini"), "head")
    database = Database(settings)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE conversations, inbound_events, products, orders, outbound_jobs, records RESTART IDENTITY CASCADE"
            )
        )
    with database.sessions.begin() as session:
        import_catalog(session, CatalogImport(**DEMO))
    yield database
    database.engine.dispose()


def test_two_customers_compete_for_last_unit(pgdb, settings):
    with pgdb.sessions.begin() as session:
        session.get(Product, "UBE-01").stock = 1
    first = checkout(pgdb, settings, psid="200")
    second = checkout(pgdb, settings, psid="300")
    accept_events(pgdb, settings, envelope(first, psid="200"))
    accept_events(pgdb, settings, envelope(second, psid="300"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: process_one(pgdb, settings), range(2)))
    while process_one(pgdb, settings):
        pass
    with pgdb.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert session.get(Product, "UBE-01").stock == 0
        assert not session.scalar(select(Inbox).where(Inbox.error.is_not(None)))


def test_concurrent_first_delivery_and_duplicate_confirmation(pgdb, settings):
    event = envelope("SHOP", mid="first")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: accept_events(pgdb, settings, event), range(8)))
    with pgdb.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Conversation)) == 1
        assert session.scalar(select(func.count()).select_from(Inbox)) == 1
    process_one(pgdb, settings)
    token = checkout(pgdb, settings)
    for _ in range(4):
        accept_events(pgdb, settings, envelope(token))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: process_one(pgdb, settings), range(8)))
    while process_one(pgdb, settings):
        pass
    with pgdb.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert session.get(Product, "UBE-01").stock == 24


def test_locked_conversation_does_not_block_other_customer(pgdb, settings):
    accept_events(pgdb, settings, envelope("SHOP", psid="200"))
    accept_events(pgdb, settings, envelope("SHOP", psid="300"))
    with pgdb.sessions.begin() as holding:
        holding.scalar(select(Conversation).where(Conversation.key == "100:200").with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(process_one, pgdb, settings).result(timeout=5)
        with pgdb.sessions() as session:
            assert session.get(Conversation, "100:300").state == "BROWSING"
            assert session.get(Conversation, "100:200").state == "IDLE"


def test_parallel_dispatch_claims_preserve_lane_order(pgdb, settings):
    from tindabot.db import enqueue

    with pgdb.sessions.begin() as session:
        for index in range(5):
            enqueue(session, key=f"sheet:{index}", destination="sheets")
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: claim_job(pgdb, time.time()), range(4)))
    assert len([c for c in claims if c]) == 1
    with pgdb.sessions() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.status == "processing")
            )
            == 1
        )


def test_migration_roundtrip(pgdb):
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    with pgdb.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_concurrent_reuse_of_status_command_does_not_apply_twice(pgdb, settings):
    from test_orders import confirm_order

    from tindabot.orders import change_status

    order = confirm_order(pgdb, settings)

    def apply(_):
        with pgdb.sessions.begin() as session:
            return change_status(session, order.id, 1, "cancelled", "same-command")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, range(2)))
    assert results[0] == results[1]
    with pgdb.sessions() as session:
        assert session.get(Product, "UBE-01").stock == 25
