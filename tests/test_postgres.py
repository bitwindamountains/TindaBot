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


def test_erasure_locks_order_jobs_against_concurrent_claims(pgdb, settings):
    from test_orders import confirm_order

    from tindabot.privacy import erase_customer

    order = confirm_order(pgdb, settings)
    with pgdb.sessions.begin() as erasing:
        erase_customer(erasing, "100:200")
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(claim_job, pgdb, time.time()).result(timeout=5) is None
    claimed = claim_job(pgdb, time.time())
    assert claimed.business_key.startswith("erasure:")
    with pgdb.sessions() as session:
        assert "name" not in session.get(Order, order.id).details
        assert not session.scalar(
            select(Outbox).where(
                Outbox.status == "processing", ~Outbox.business_key.like("erasure:%")
            )
        )


def test_postgres_all_time_search_uses_customer_json_and_literal_wildcards(pgdb, settings):
    from test_orders import confirm_order

    order = confirm_order(pgdb, settings)
    with pgdb.sessions.begin() as session:
        stored = session.get(Order, order.id)
        stored.created_at = time.time() - 45 * 86400
        stored.details = {**stored.details, "name": "Queue_100% Customer"}
    with TestClient(create_app(settings, pgdb)) as client:
        headers = {"Authorization": "Bearer " + "a" * 40}
        data = client.get(
            "/admin/workspace", params={"scope": "open", "q": "queue_100%"}, headers=headers
        ).json()
        assert data["orders"][0]["id"] == order.id and data["summary"]["pending"] == 1
        data = client.get(
            "/admin/workspace", params={"scope": "all", "q": "queue_100_"}, headers=headers
        ).json()
        assert data["order_total"] == 0


def test_erasure_waits_for_claim_then_refuses_processing_job(pgdb, settings):
    from threading import Event

    from sqlalchemy import event
    from test_orders import confirm_order

    from tindabot.privacy import erase_customer

    order = confirm_order(pgdb, settings)
    checking_jobs = Event()

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if (
            "FROM outbound_jobs" in statement
            and "ORDER BY outbound_jobs.id FOR UPDATE" in statement
        ):
            checking_jobs.set()

    def erase():
        with pgdb.sessions.begin() as session:
            erase_customer(session, "100:200")

    event.listen(pgdb.engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pgdb.sessions.begin() as claiming:
                job = claiming.scalar(
                    select(Outbox)
                    .where(Outbox.order_id == order.id, Outbox.destination == "sheets")
                    .with_for_update()
                )
                job.status = "processing"
                claiming.flush()
                result = pool.submit(erase)
                assert checking_jobs.wait(timeout=5)
            with pytest.raises(ValueError, match="delivery_in_progress"):
                result.result(timeout=5)
    finally:
        event.remove(pgdb.engine, "before_cursor_execute", observe)
    with pgdb.sessions() as session:
        assert "name" in session.get(Order, order.id).details


@pytest.mark.parametrize("same_command", [True, False])
def test_concurrent_refund_records_cannot_double_the_balance(pgdb, settings, same_command):
    from test_orders import confirm_order

    from tindabot.db import OrderActivity
    from tindabot.orders import OrderConflict, apply_order_action, change_status, refund_total

    order = confirm_order(pgdb, settings)
    with pgdb.sessions.begin() as session:
        change_status(session, order.id, 1, "paid", "journal-paid")
        change_status(session, order.id, 2, "cancelled", "journal-cancel")

    def record(index):
        try:
            with pgdb.sessions.begin() as session:
                return apply_order_action(
                    session,
                    order.id,
                    3,
                    "same-refund" if same_command else f"refund-{index}",
                    "refund",
                    "TEST-REFERENCE",
                    amount_minor=26000,
                )
        except OrderConflict as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(record, range(2)))
    if same_command:
        assert results[0] == results[1]
    else:
        assert sum(isinstance(result, dict) for result in results) == 1
        assert "version_conflict" in results
    with pgdb.sessions() as session:
        assert refund_total(session, order.id) == 26000
        assert session.get(Order, order.id).payment_status == "refunded"
        assert (
            session.scalar(
                select(func.count())
                .select_from(OrderActivity)
                .where(OrderActivity.kind == "refund")
            )
            == 1
        )


def test_new_activity_table_is_not_granted_to_public(pgdb):
    with pgdb.sessions() as session:
        grants = session.execute(
            text("""
            SELECT privilege_type FROM information_schema.table_privileges
            WHERE table_name = 'order_activity' AND grantee IN ('PUBLIC', 'anon', 'authenticated')
        """)
        ).all()
        assert grants == []
