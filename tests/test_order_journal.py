import time

import pytest
from sqlalchemy import func, select
from test_orders import confirm_order

from tindabot.db import Order, OrderActivity, Product, Record
from tindabot.orders import change_status
from tindabot.privacy import erase_customer
from tindabot.worker import maintenance

AUTH = {"Authorization": "Bearer " + "a" * 40}


def refundable(db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        change_status(session, order.id, 1, "paid", "payment")
        change_status(session, order.id, 2, "cancelled", "cancel")
    return order.id


def test_private_notes_require_operator_and_retry_without_duplication(client, db, settings):
    order = confirm_order(db, settings)
    path = f"/admin/orders/{order.id}/notes"
    body = {
        "command_id": "private-note",
        "expected_version": 1,
        "body": "  Leave the gift tag blank.  ",
    }
    assert client.post(path, json=body).status_code == 401
    assert (
        client.post(path, json=body, headers={"Authorization": "Bearer " + "b" * 40}).status_code
        == 401
    )
    first = client.post(path, json=body, headers=AUTH)
    assert first.status_code == 200
    assert client.post(path, json=body, headers=AUTH).json() == first.json()
    assert (
        client.post(path, json={**body, "body": "Different note"}, headers=AUTH).status_code == 409
    )
    assert (
        client.post(path, json={**body, "command_id": "stale-note"}, headers=AUTH).status_code
        == 409
    )
    detail = client.get(f"/admin/workspace/orders/{order.id}", headers=AUTH).json()
    assert detail["version"] == 2
    assert [e["kind"] for e in detail["activity"]] == ["note", "created"]
    assert detail["activity"][0]["body"] == "Leave the gift tag blank."
    with db.sessions() as session:
        assert "Leave the gift" not in str(session.get(Record, "command:private-note").value)
    assert (
        client.post(
            path,
            json={**body, "command_id": "empty", "expected_version": 2, "body": "   "},
            headers=AUTH,
        ).status_code
        == 409
    )


def test_partial_and_complete_refund_reconciliation(client, db, settings):
    order_id = refundable(db, settings)
    path = f"/admin/orders/{order_id}/refunds"
    body = {
        "command_id": "refund-1",
        "expected_version": 3,
        "amount_minor": 10000,
        "reference": "BANK-TEST-1",
    }
    assert client.post(path, json=body).status_code == 401
    assert (
        client.post(path, json=body, headers={"Authorization": "Bearer " + "b" * 40}).status_code
        == 401
    )
    first = client.post(path, json=body, headers=AUTH)
    assert first.status_code == 200
    assert first.json()["payment_status"] == "refund_required"
    assert first.json()["refunded_minor"] == 10000
    assert client.post(path, json=body, headers=AUTH).json() == first.json()
    assert (
        client.post(path, json={**body, "reference": "different"}, headers=AUTH).status_code == 409
    )
    assert (
        client.post(
            path,
            json={**body, "command_id": "too-much", "expected_version": 4, "amount_minor": 16001},
            headers=AUTH,
        ).status_code
        == 409
    )
    second = client.post(
        path,
        json={**body, "command_id": "refund-2", "expected_version": 4, "amount_minor": 16000},
        headers=AUTH,
    )
    assert second.json()["payment_status"] == "refunded"
    assert second.json()["refunded_minor"] == 26000
    data = client.get("/admin/workspace?scope=all&payment=refunded", headers=AUTH).json()
    assert data["orders"][0]["id"] == order_id
    assert client.get("/admin/workspace?scope=open", headers=AUTH).json()["orders"] == []
    detail = client.get(f"/admin/workspace/orders/{order_id}", headers=AUTH).json()
    assert [e["kind"] for e in detail["activity"]] == [
        "refund",
        "refund",
        "status",
        "status",
        "created",
    ]
    with db.sessions() as session:
        assert session.get(Product, "UBE-01").stock == 25
        assert (
            session.scalar(
                select(func.count())
                .select_from(OrderActivity)
                .where(OrderActivity.kind == "refund")
            )
            == 2
        )
    assert (
        client.post(
            path, json={**body, "command_id": "extra", "expected_version": 5}, headers=AUTH
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"amount_minor": 0}, 422),
        ({"amount_minor": 1.5}, 422),
        ({"reference": "   "}, 409),
        ({"completed_at": 1}, 409),
        ({"completed_at": time.time() + 86400}, 409),
    ],
)
def test_invalid_refunds_leave_ledger_and_balance_unchanged(client, db, settings, changes, code):
    order_id = refundable(db, settings)
    body = {
        "command_id": "invalid",
        "expected_version": 3,
        "amount_minor": 100,
        "reference": "TEST",
        **changes,
    }
    assert (
        client.post(f"/admin/orders/{order_id}/refunds", json=body, headers=AUTH).status_code
        == code
    )
    with db.sessions() as session:
        assert session.get(Order, order_id).version == 3
        assert not session.scalar(select(OrderActivity).where(OrderActivity.kind == "refund"))


def test_refund_cannot_be_recorded_on_uncancelled_order(client, db, settings):
    order = confirm_order(db, settings)
    response = client.post(
        f"/admin/orders/{order.id}/refunds",
        headers=AUTH,
        json={
            "command_id": "no-refund",
            "expected_version": 1,
            "amount_minor": 100,
            "reference": "TEST",
        },
    )
    assert response.status_code == 409


@pytest.mark.parametrize("method", ["erasure", "retention"])
def test_privacy_scrubs_notes_and_references_but_preserves_refund_ledger(
    client, db, settings, method
):
    order_id = refundable(db, settings)
    assert (
        client.post(
            f"/admin/orders/{order_id}/notes",
            headers=AUTH,
            json={
                "command_id": "note-pii",
                "expected_version": 3,
                "body": "Private customer instruction",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/admin/orders/{order_id}/refunds",
            headers=AUTH,
            json={
                "command_id": "refund-pii",
                "expected_version": 4,
                "amount_minor": 100,
                "reference": "Private reference",
            },
        ).status_code
        == 200
    )
    if method == "erasure":
        with db.sessions.begin() as session:
            erase_customer(session, "100:200")
    else:
        maintenance(db, settings, now=time.time() + (settings.order_pii_retention_days + 1) * 86400)
    detail = client.get(f"/admin/workspace/orders/{order_id}", headers=AUTH).json()
    assert detail["anonymized"] and detail["refunded_minor"] == 100
    assert all(e["body"] is None for e in detail["activity"])
    assert (
        client.post(
            f"/admin/orders/{order_id}/notes",
            headers=AUTH,
            json={
                "command_id": "after-erasure",
                "expected_version": detail["version"],
                "body": "New PII",
            },
        ).status_code
        == 409
    )
    # Financial reconciliation can continue without retaining a new reference.
    assert (
        client.post(
            f"/admin/orders/{order_id}/refunds",
            headers=AUTH,
            json={
                "command_id": "after-erasure-refund",
                "expected_version": detail["version"],
                "amount_minor": 25900,
            },
        ).status_code
        == 200
    )


def test_activity_is_bounded_private_and_scoped_to_order(client, db, settings):
    order = confirm_order(db, settings)
    with db.sessions.begin() as session:
        for index in range(55):
            session.add(
                OrderActivity(
                    order_id=order.id,
                    kind="note",
                    actor="operator",
                    order_version=2 + index,
                    occurred_at=time.time(),
                    body=f"Note {index}",
                )
            )
    path = f"/admin/workspace/orders/{order.id}/activity"
    assert client.get(path).status_code == 401
    first = client.get(path, headers=AUTH)
    assert first.headers["cache-control"] == "no-store"
    first = first.json()
    assert len(first["activity"]) == 50
    second = client.get(path, headers=AUTH, params={"before": first["next_activity_cursor"]}).json()
    assert len(second["activity"]) == 6 and second["next_activity_cursor"] is None
    assert len({e["id"] for e in first["activity"] + second["activity"]}) == 56
    assert client.get("/admin/workspace/orders/missing/activity", headers=AUTH).status_code == 404
