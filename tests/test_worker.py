import time
from unittest.mock import Mock

from conftest import envelope, send
from sqlalchemy import func, select
from test_orders import confirm_order

from tindabot.db import Conversation, Inbox, Order, Outbox, Product
from tindabot.events import accept_events
from tindabot.integrations import DeliveryError
from tindabot.service import process_one
from tindabot.worker import claim_job, dispatch_one, maintenance


def test_dry_run_never_calls_external_provider(db, settings):
    send(db, settings, "hi")
    adapter = Mock()
    assert dispatch_one(db, settings, adapter)
    adapter.send_message.assert_not_called()
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "dry_run"


def test_expired_window_suppresses_queued_reply(db, settings):
    send(db, settings, "hi")
    adapter = Mock()
    assert dispatch_one(db, settings, adapter, now=time.time() + 86401)
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "suppressed"


def test_seller_echo_pauses_but_own_echo_does_not(db, settings):
    send(db, settings, "hi")
    accept_events(db, settings, envelope("outgoing", echo=True, app_id="900"))
    process_one(db, settings)
    with db.sessions() as session:
        assert not session.get(Conversation, "100:200").paused
    accept_events(db, settings, envelope("seller reply", echo=True))
    process_one(db, settings)
    with db.sessions() as session:
        assert session.get(Conversation, "100:200").paused
    dispatch_one(db, settings, Mock())
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "suppressed"


def test_handover_silent_until_menu(db, settings):
    send(db, settings, "SELLER")
    with db.sessions() as session:
        count = session.scalar(select(func.count()).select_from(Outbox))
    send(db, settings, "SHOP")
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Outbox)) == count
    send(db, settings, "MENU")
    with db.sessions() as session:
        assert not session.get(Conversation, "100:200").paused


def test_abandoned_send_becomes_uncertain_without_duplicate_send(db, settings):
    send(db, settings, "hi")
    now = time.time()
    job = claim_job(db, now)
    assert job.status == "processing"
    assert claim_job(db, now + 121) is None
    with db.sessions() as session:
        assert session.get(Outbox, job.id).status == "uncertain"


def test_ambiguous_timeout_requires_operator_resolution(db, settings):
    send(db, settings, "hi")
    settings.delivery_mode = "live"  # Test adapter only; no credential-bearing construction.
    adapter = Mock()
    adapter.send_message.side_effect = DeliveryError("timeout", uncertain=True)
    dispatch_one(db, settings, adapter)
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "uncertain"


def test_retryable_failure_retries_independently(db, settings):
    send(db, settings, "hi")
    settings.delivery_mode = "live"
    adapter = Mock()
    adapter.send_message.side_effect = DeliveryError("throttled", retry=True)
    now = time.time()
    dispatch_one(db, settings, adapter, now=now)
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "pending"
    adapter.send_message.side_effect = None
    adapter.send_message.return_value = "sent-mid"
    dispatch_one(db, settings, adapter, now=now + 10)
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "delivered"


def test_retention_scrubs_payloads_and_queues_sheet_update(db, settings):
    order = confirm_order(db, settings)
    now = time.time()
    with db.sessions.begin() as session:
        session.get(Order, order.id).created_at = now - 400 * 86400
        for event in session.scalars(select(Inbox)):
            event.received_at = now - 10 * 86400
        c = session.get(Conversation, "100:200")
        c.context = {"name": "Personal data"}
        c.updated_at = now - 90000
    maintenance(db, settings, now)
    with db.sessions() as session:
        assert session.get(Order, order.id).anonymized
        assert "name" not in session.get(Order, order.id).details
        assert session.get(Conversation, "100:200").context == {}
        assert all(event.payload == {} for event in session.scalars(select(Inbox)))
        assert session.scalar(select(Outbox).where(Outbox.business_key == f"retention:{order.id}"))


def test_unpaid_expiry_returns_inventory_once(db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        session.get(Order, order.id).expires_at = time.time() - 10
    maintenance(db, settings)
    maintenance(db, settings, now=time.time() + 65)
    with db.sessions() as session:
        assert session.get(Order, order.id).status == "cancelled"
        assert session.get(Product, "UBE-01").stock == 25


def test_handover_command_bypasses_customer_rate_limit(db, settings):
    settings.max_messages_per_minute = 1
    send(db, settings, "hi")
    send(db, settings, "SELLER")
    with db.sessions() as session:
        assert session.get(Conversation, "100:200").paused


def test_network_send_does_not_hold_database_connection(db, settings):
    send(db, settings, "hi")
    settings.delivery_mode = "live"
    adapter = Mock()

    def send_without_transaction(*_):
        assert db.engine.pool.checkedout() == 0
        return "sent-outside-transaction"

    adapter.send_message.side_effect = send_without_transaction
    dispatch_one(db, settings, adapter)
    with db.sessions() as session:
        assert session.scalar(select(Outbox)).status == "delivered"


def test_draft_expires_even_when_paused_customer_keeps_messaging(db, settings):
    from conftest import checkout

    checkout(db, settings)
    now = time.time()
    with db.sessions.begin() as session:
        conversation = session.get(Conversation, "100:200")
        conversation.context = {**conversation.context, "draft_created_at": now - 90000}
        conversation.updated_at = now
        conversation.paused = True
    maintenance(db, settings, now=now)
    with db.sessions() as session:
        conversation = session.get(Conversation, "100:200")
        assert conversation.context == {}
        assert conversation.paused
