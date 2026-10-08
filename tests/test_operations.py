import json
import logging
import time
from unittest.mock import Mock

import pytest
from conftest import send
from sqlalchemy import select
from test_orders import confirm_order

from tindabot.db import Conversation, Inbox, Order, Outbox, Record
from tindabot.logging_setup import SafeFormatter
from tindabot.privacy import erase_customer
from tindabot.worker import dispatch_one, sync_seller


def test_status_endpoint_enforces_versions_and_scoped_auth(client, db, settings):
    order = confirm_order(db, settings)
    headers = {"Authorization": "Bearer " + "b" * 40}
    body = {
        "command_id": "seller-confirm",
        "order_id": order.id,
        "expected_version": 1,
        "status": "confirmed",
    }
    assert client.post("/admin/order-status", json=body, headers=headers).status_code == 200
    assert client.post("/admin/order-status", json=body, headers=headers).status_code == 200
    body.update(command_id="stale", status="cancelled")
    assert client.post("/admin/order-status", json=body, headers=headers).status_code == 409
    assert (
        client.post("/admin/automation", json={"enabled": False}, headers=headers).status_code
        == 401
    )


def test_uncertain_job_cannot_be_blindly_retried(client, db, settings):
    send(db, settings, "hi")
    with db.sessions.begin() as session:
        job = session.scalar(select(Outbox))
        job.status = "uncertain"
        job_id = job.id
    headers = {"Authorization": "Bearer " + "a" * 40}
    path = f"/admin/jobs/{job_id}/resolve"
    assert client.post(path, json={"action": "retry"}, headers=headers).status_code == 409
    assert client.post(path, json={"action": "suppress"}, headers=headers).status_code == 200


def test_seller_polling_imports_status_and_preserves_command_idempotency(db, settings):
    order = confirm_order(db, settings)
    settings.delivery_mode = "live"
    adapter = Mock()
    from tindabot.catalog import CatalogImport
    from tindabot.cli import DEMO

    adapter.read_catalog.return_value = CatalogImport(**DEMO)
    adapter.commands.return_value = [(2, ["cmd-1", order.id, "1", "confirmed", ""])]
    now = time.time()
    sync_seller(db, settings, adapter, now)
    sync_seller(db, settings, adapter, now + 61)
    with db.sessions() as session:
        assert session.get(Order, order.id).status == "confirmed"
        assert session.get(Order, order.id).version == 2
        assert session.get(Record, "seller-sync").value["ok"]
    assert adapter.command_result.call_args.args[-1] == "accepted"


def test_seller_poll_error_does_not_discard_good_catalog(db, settings):
    settings.delivery_mode = "live"
    adapter = Mock()
    adapter.read_catalog.side_effect = RuntimeError("Provider unavailable")
    sync_seller(db, settings, adapter)
    with db.sessions() as session:
        assert session.get(Record, "catalog").value["version"] == 1
        assert not session.get(Record, "seller-sync").value["ok"]


def test_erase_scrubs_all_controlled_text_and_preserves_financial_totals(db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        result = erase_customer(session, "100:200")
        assert result["orders"] == 1
    with db.sessions() as session:
        o = session.get(Order, order.id)
        assert o.total_minor == 26000
        assert "name" not in o.details
        assert session.get(Conversation, "100:200").paused
        assert all(event.payload == {} for event in session.scalars(select(Inbox)))
        assert all(
            job.payload == {}
            for job in session.scalars(select(Outbox).where(Outbox.conversation_key == "100:200"))
        )


def test_erase_refuses_to_race_with_inflight_send(db, settings):
    send(db, settings, "hi")
    with db.sessions.begin() as session:
        session.scalar(select(Outbox)).status = "processing"
    with db.sessions.begin() as session, pytest.raises(ValueError, match="delivery_in_progress"):
        erase_customer(session, "100:200")


@pytest.mark.parametrize("destination", ["sheets", "email"])
def test_erase_refuses_inflight_order_linked_delivery(db, settings, destination):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        job = session.scalar(
            select(Outbox).where(Outbox.order_id == order.id, Outbox.destination == destination)
        )
        assert job.conversation_key is None
        job.status = "processing"
    with db.sessions.begin() as session, pytest.raises(ValueError, match="delivery_in_progress"):
        erase_customer(session, "100:200")
    with db.sessions() as session:
        assert "name" in session.get(Order, order.id).details


def test_erase_suppresses_order_jobs_but_preserves_delivery_history(db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        job = session.scalar(select(Outbox).where(Outbox.destination == "email"))
        job.status = "delivered"
        email_id = job.id
    with db.sessions.begin() as session:
        erase_customer(session, "100:200")
    with db.sessions() as session:
        assert session.get(Outbox, email_id).status == "delivered"
        original = session.scalar(
            select(Outbox).where(Outbox.business_key == f"sheet:{order.id}:1")
        )
        assert original.status == "suppressed"
        cleanup = session.scalar(select(Outbox).where(Outbox.business_key.like("erasure:%")))
        assert cleanup.status == "pending"


def test_invalid_catalog_does_not_block_commands_and_health_recovers(db, settings):
    from tindabot.catalog import CatalogImport
    from tindabot.cli import DEMO

    order = confirm_order(db, settings)
    settings.delivery_mode = "live"
    adapter = Mock()
    adapter.read_catalog.side_effect = ValueError("Invalid price")
    adapter.commands.return_value = [(2, ["independent-command", order.id, "1", "confirmed", ""])]
    now = time.time()
    sync_seller(db, settings, adapter, now)
    with db.sessions() as session:
        assert session.get(Order, order.id).status == "confirmed"
        health = session.get(Record, "seller-sync").value
        assert not health["ok"] and not health["catalog"]["ok"]
        assert health["commands"]["ok"]
        assert session.get(Record, "catalog").value["version"] == 1
    adapter.command_result.assert_called_once_with(
        2, adapter.commands.return_value[0][1], "accepted"
    )
    adapter.read_catalog.side_effect = None
    adapter.read_catalog.return_value = CatalogImport(**DEMO)
    sync_seller(db, settings, adapter, now + 61)
    with db.sessions() as session:
        assert session.get(Order, order.id).version == 2
        health = session.get(Record, "seller-sync").value
        assert health["ok"] and "error" not in health["catalog"]


def test_command_provider_failure_keeps_successful_catalog_refresh(db, settings):
    from tindabot.catalog import CatalogImport
    from tindabot.cli import DEMO

    settings.delivery_mode = "live"
    adapter = Mock()
    adapter.read_catalog.return_value = CatalogImport(**DEMO)
    adapter.commands.side_effect = RuntimeError("Commands unavailable")
    sync_seller(db, settings, adapter)
    with db.sessions() as session:
        health = session.get(Record, "seller-sync").value
        assert health["catalog"]["ok"] and not health["commands"]["ok"]
        assert session.get(Record, "catalog").value["version"] == 2


def test_superseded_prompt_is_suppressed(db, settings):
    send(db, settings, "hi")
    send(db, settings, "SHOP")
    adapter = Mock()
    dispatch_one(db, settings, adapter)
    with db.sessions() as session:
        assert session.scalar(select(Outbox).order_by(Outbox.id).limit(1)).status == "suppressed"


def test_safe_log_formatter_excludes_exception_and_arguments():
    record = logging.LogRecord("httpx", logging.ERROR, "", 0, "token=%s", ("secret-value",), None)
    payload = SafeFormatter().format(record)
    assert "secret-value" not in payload
    assert json.loads(payload)["event"] == "httpx"
