import time

import pytest
from conftest import checkout, envelope, send
from sqlalchemy import func, select

from tindabot.catalog import CatalogImport, adjust_stock, import_catalog
from tindabot.db import Conversation, Inbox, Order, Outbox, Product, Record
from tindabot.events import accept_events
from tindabot.orders import OrderConflict, change_status
from tindabot.service import process_one, view_for


def confirm_order(db, settings):
    token = checkout(db, settings)
    send(db, settings, token)
    with db.sessions() as session:
        return session.scalar(select(Order))


def test_delivery_checkout_and_distinct_duplicate_confirm(db, settings):
    token = checkout(db, settings)
    send(db, settings, token)
    send(db, settings, token)
    with db.sessions() as session:
        order = session.scalar(select(Order))
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert order.total_minor == 26000
        assert order.details["phone"] == "09171234567"
        assert session.get(Product, "UBE-01").stock == 24
        assert (
            session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.order_id == order.id)
            )
            == 2
        )


def test_price_change_requires_new_confirmation(db, settings):
    token = checkout(db, settings)
    with db.sessions.begin() as session:
        session.get(Product, "UBE-01").price_minor = 20000
    send(db, settings, token)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        ctx = session.get(Conversation, "100:200").context
        assert ctx["version"] == 2
        assert ctx["quote"]["total_minor"] == 28000
    send(db, settings, token)
    send(db, settings, f"CONFIRM:{ctx['checkout_id']}:2")
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_worker_failure_rolls_back_all_business_effects_then_retries(db, settings):
    token = checkout(db, settings)
    now = time.time()
    accept_events(db, settings, envelope(token, now=now))

    def crash():
        raise RuntimeError("simulated process failure")

    assert process_one(db, settings, now=now, before_commit=crash)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.get(Product, "UBE-01").stock == 25
        assert session.scalar(select(Inbox).order_by(Inbox.id.desc()).limit(1)).status == "pending"
    assert process_one(db, settings, now=now + 10)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1
        assert session.get(Product, "UBE-01").stock == 24


def test_out_of_stock_does_not_create_order(db, settings):
    token = checkout(db, settings)
    with db.sessions.begin() as session:
        session.get(Product, "UBE-01").stock = 0
    send(db, settings, token)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.get(Conversation, "100:200").state == "CART"


def test_tracking_filters_owner(db, settings):
    order = confirm_order(db, settings)
    send(db, settings, "TRACK", psid="300")
    with db.sessions() as session:
        own = view_for(session, session.get(Conversation, "100:200"), settings, time.time())
        other = view_for(session, session.get(Conversation, "100:300"), settings, time.time())
        assert order.code in own["tracking"]
        assert order.code not in other["tracking"]


def test_cancel_releases_stock_exactly_once(db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        first = change_status(session, order.id, 1, "cancelled", "cancel-once")
    with db.sessions.begin() as session:
        assert change_status(session, order.id, 1, "cancelled", "cancel-once") == first
        assert session.get(Product, "UBE-01").stock == 25
        with pytest.raises(OrderConflict):
            change_status(session, order.id, 2, "shipped", "ship-cancelled")


def test_catalog_refresh_preserves_sold_stock(db, settings):
    confirm_order(db, settings)
    from tindabot.cli import DEMO

    with db.sessions.begin() as session:
        import_catalog(session, CatalogImport(**DEMO))
        assert session.get(Product, "UBE-01").stock == 24
        first = adjust_stock(session, "UBE-01", 10, "restock-1")
        assert first == adjust_stock(session, "UBE-01", 10, "restock-1")
        assert session.get(Product, "UBE-01").stock == 34


def test_pickup_skips_address_and_shipping(db, settings):
    for value in [
        "PRODUCT:UBE-01",
        "1",
        "CHECKOUT",
        "DELIVERY:pickup",
        "María 李",
        "+639171234567",
        "PAY:cod",
    ]:
        send(db, settings, value)
    with db.sessions() as session:
        ctx = session.get(Conversation, "100:200").context
        assert ctx["quote"]["shipping_minor"] == 0
        assert not ctx.get("address")
    send(db, settings, f"CONFIRM:{ctx['checkout_id']}:{ctx['version']}")
    with db.sessions() as session:
        assert session.scalar(select(Order)).total_minor == 18000


def test_stale_catalog_blocks_confirmation(db, settings):
    token = checkout(db, settings)
    with db.sessions.begin() as session:
        session.get(Record, "catalog").updated_at = time.time() - 10000
    send(db, settings, token)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_invalid_phone_then_cancel(db, settings):
    for value in [
        "PRODUCT:UBE-01",
        "1",
        "CHECKOUT",
        "DELIVERY:delivery",
        "Juan Cruz",
        "123",
        "abc",
        "foo",
    ]:
        send(db, settings, value)
    with db.sessions() as session:
        c = session.get(Conversation, "100:200")
        assert c.state == "PHONE"
        assert c.context["phone_failures"] == 3
    send(db, settings, "CANCEL")
    with db.sessions() as session:
        assert session.get(Conversation, "100:200").context == {}
