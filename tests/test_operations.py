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
