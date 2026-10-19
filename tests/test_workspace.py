import time

import pytest
from conftest import checkout, send
from sqlalchemy import func, select

from tindabot.db import Conversation, Inbox, Order, Outbox, Record

AUTH = {"Authorization": "Bearer " + "a" * 40}


def test_old_unfinished_orders_are_counted_and_searchable(client, db, settings):
    send(db, settings, checkout(db, settings))
    with db.sessions.begin() as session:
        order = session.query(Order).one()
        order.created_at = time.time() - 45 * 86400
        order_id = order.id
    period = client.get("/admin/workspace?days=30", headers=AUTH).json()
    assert period["summary"]["orders"] == 0
    assert period["summary"]["pending"] == 1
    assert period["orders"] == []
    data = client.get("/admin/workspace?scope=open&status=pending&q=juan", headers=AUTH).json()
    assert data["order_total"] == 1
    assert data["orders"][0]["id"] == order_id
    assert client.get("/admin/workspace?scope=all&q=%25", headers=AUTH).json()["orders"] == []
    with db.sessions.begin() as session:
        order = session.get(Order, order_id)
        order.status, order.payment_status = "cancelled", "refund_required"
    data = client.get("/admin/workspace?scope=open&payment=refund_required", headers=AUTH).json()
    assert data["order_total"] == 1
    assert data["order_counts"] == {"cancelled": 1}


@pytest.mark.parametrize("sort", ["newest", "oldest", "highest", "lowest"])
def test_order_cursor_has_stable_ties_and_excludes_new_insertions(client, db, settings, sort):
    send(db, settings, checkout(db, settings))
    now = time.time() - 60
    with db.sessions.begin() as session:
        template = session.query(Order).one()
        template.created_at = now - 1000
        for index in range(205):
            session.add(
                Order(
                    id=f"page-{index:03}",
                    code=f"TB-PAGE-{index:03}",
                    checkout_id=f"checkout-{index}",
                    conversation_key=template.conversation_key,
                    details={"name": "Queue customer"},
                    items=[],
                    total_minor=500,
                    shipping_minor=0,
                    created_at=now,
                )
            )
    params = {"scope": "all", "q": "Queue customer", "sort": sort}
    first = client.get("/admin/workspace", params=params, headers=AUTH).json()
    assert len(first["orders"]) == 200 and first["order_total"] == 205
    assert first["summary"]["order_value"] == 205 * 500 + 26000
    with db.sessions.begin() as session:
        session.add(
            Order(
                id="new-insertion",
                code="TB-NEW",
                checkout_id="new-checkout",
                conversation_key="100:200",
                details={"name": "Queue customer"},
                items=[],
                total_minor=500,
                shipping_minor=0,
            )
        )
    second = client.get(
        "/admin/workspace", params={**params, "cursor": first["next_cursor"]}, headers=AUTH
    ).json()
    assert len(second["orders"]) == 5 and second["next_cursor"] is None
    ids = [o["id"] for o in first["orders"] + second["orders"]]
    assert ids == [f"page-{index:03}" for index in range(205)]
    assert (
        client.get(
            "/admin/workspace",
            params={**params, "q": "different", "cursor": first["next_cursor"]},
            headers=AUTH,
        ).status_code
        == 422
    )
    assert client.get("/admin/workspace?cursor=invalid", headers=AUTH).status_code == 422


def test_shell_is_public_but_customer_data_requires_operator(client):
    shell = client.get("/")
    assert shell.status_code == 200
    assert "frame-ancestors 'none'" in shell.headers["content-security-policy"]
    assert "Juan Dela Cruz" not in shell.text
    assert client.get("/assets/app.js").status_code == 200
    effect = client.get("/assets/effects/hero.js", headers={"Accept-Encoding": "gzip"})
    assert effect.status_code == 200
    assert effect.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in effect.headers["vary"].lower()
    assert "mountHero" in effect.text
    assert client.get("/admin/workspace").status_code == 401
    assert client.get("/admin/workspace/orders/missing").status_code == 401
    assert (
        client.get("/admin/workspace", headers={"Authorization": "Bearer " + "b" * 40}).status_code
        == 401
    )


def test_snapshot_totals_private_details_and_status_updates(client, db, settings):
    send(db, settings, checkout(db, settings))
    response = client.get("/admin/workspace", headers=AUTH)
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["summary"]["orders"] == 1
    assert data["summary"]["pending"] == 1
    assert len(data["series"]) == 7
    order = data["orders"][0]
    assert data["summary"]["order_value"] == order["total_minor"]
    assert sum(day["value"] for day in data["series"]) == order["total_minor"]
    assert "phone" not in order and "details" not in order
    detail = client.get(f"/admin/workspace/orders/{order['id']}", headers=AUTH)
    assert detail.headers["cache-control"] == "no-store"
    assert detail.json()["details"]["phone"] == "09171234567"
    assert detail.json()["created_at"] == order["created_at"]
    assert data["job_health"] == {
        "inbox_failed": 0,
        "delivery_failed": 0,
        "delivery_uncertain": 0,
    }
    changed = client.post(
        "/admin/order-status",
        headers=AUTH,
        json={
            "command_id": "workspace-cancel",
            "order_id": order["id"],
            "expected_version": order["version"],
            "status": "cancelled",
        },
    )
    assert changed.status_code == 200
    data = client.get("/admin/workspace", headers=AUTH).json()
    assert data["summary"]["orders"] == 1
    assert data["summary"]["order_value"] == 0
    assert data["summary"]["pending"] == 0
    assert all(day["value"] == 0 for day in data["series"])


def test_period_bounds_and_server_automation_override(client, db, settings):
    send(db, settings, checkout(db, settings))
    with db.sessions.begin() as session:
        order = session.query(Order).one()
        order.created_at = time.time() - 15 * 86400
        session.add(Record(key="automation", value={"enabled": True}))
    assert client.get("/admin/workspace?days=7", headers=AUTH).json()["summary"]["orders"] == 0
    data = client.get("/admin/workspace?days=30", headers=AUTH).json()
    assert data["summary"]["orders"] == 1
    assert len(data["series"]) == 30
    assert sum(day["value"] for day in data["series"]) == data["summary"]["order_value"]
    assert client.get("/admin/workspace?days=999", headers=AUTH).status_code == 422
    settings.automation_enabled = False
    data = client.get("/admin/workspace", headers=AUTH).json()
    assert data["automation"] is False and data["automation_locked"] is True
    assert client.get("/admin/workspace/orders/missing", headers=AUTH).status_code == 404


def test_diagnostics_distinguish_failed_events_and_uncertain_deliveries(client, db, settings):
    send(db, settings, checkout(db, settings))
    with db.sessions.begin() as session:
        event = session.query(Inbox).first()
        event.status = "failed"
        session.add_all(
            [
                Outbox(
                    business_key="diagnostic-failed",
                    lane="diagnostic-a",
                    destination="messenger",
                    status="failed",
                ),
                Outbox(
                    business_key="diagnostic-uncertain",
                    lane="diagnostic-b",
                    destination="smtp",
                    status="uncertain",
                ),
            ]
        )
    data = client.get("/admin/workspace", headers=AUTH).json()
    assert data["job_health"] == {
        "inbox_failed": 1,
        "delivery_failed": 1,
        "delivery_uncertain": 1,
    }
    assert data["failures"] == 3


def test_insights_count_self_served_conversations_and_group_missed_questions(client, db, settings):
    send(db, settings, "how much po?", psid="201")  # FAQ hit: handled by the bot
    send(db, settings, "May size small pa po?", psid="202")
    send(db, settings, "may size small pa po", psid="203")
    send(db, settings, "SELLER", psid="204")
    with db.sessions() as session:
        flags = {
            e.payload["value"]: e.payload.get("missed") for e in session.scalars(select(Inbox))
        }
    assert flags["how much po?"] is None and flags["May size small pa po?"] is True
    insights = client.get("/admin/workspace", headers=AUTH).json()["insights"]
    assert insights["conversations"] == 4
    assert insights["needed_you"] == 3 and insights["self_served"] == 1
    assert insights["missed_week"] == 2
    assert insights["misses"] == [
        {
            "text": "may size small pa po",
            "keywords": "may size small pa po",
            "count": 2,
            "last_at": insights["misses"][0]["last_at"],
        }
    ]


def chat(client, value, state="IDLE", context=None, headers=AUTH):
    body = {"state": state, "context": context or {}, "value": value}
    return client.post("/admin/workspace/test-chat", json=body, headers=headers)


def test_test_chat_walks_checkout_without_saving_or_pausing(client, db, settings):
    reply = chat(client, "2 ube pandesal po").json()
    assert reply["state"] == "CART" and reply["context"]["cart"] == {"UBE-01": 2}
    state, context = reply["state"], reply["context"]
    for value in ["CHECKOUT", "pickup", "Juan Dela Cruz", "09171234567", "cod po"]:
        reply = chat(client, value, state, context).json()
        state, context = reply["state"], reply["context"]
    # The quote runs through the same code as live checkout.
    assert state == "CONFIRMING" and context["quote"]["total_minor"] == 36000
    reply = chat(client, f"CONFIRM:{context['checkout_id']}:{context['version']}", state, context)
    assert "TEST-ORDER" in reply.json()["replies"][0]["text"]
    assert chat(client, "pakausap sa seller").json()["handed_over"]
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
        assert session.scalar(select(func.count()).select_from(Conversation)) == 0


def test_test_chat_requires_operator_and_rejects_forged_state(client):
    assert chat(client, "hi", headers={"Authorization": "Bearer " + "b" * 40}).status_code == 401
    assert chat(client, "1", "QTY", {"cart": "not-a-cart", "selected": "UBE-01"}).status_code == 422
    assert chat(client, "hi", "UNKNOWN").status_code == 422


def test_test_chat_rejects_forged_quotes_and_malformed_state(client):
    forged = {
        "quote": {"items": [{"qty": "x", "price_minor": 4_000_000_000, "name": "n"}]},
        "cart": {"UBE-01": 1},
        "checkout_id": "c",
        "version": 1,
        "delivery": "pickup",
        "payment": "cod",
        "name": "n",
        "phone": "09171234567",
    }
    # The browser's quote is replaced by a server quote, so the forged one never multiplies.
    reply = chat(client, "EDIT", "CONFIRMING", forged)
    assert reply.status_code == 200 and reply.json()["state"] == "DELIVERY"
    assert chat(client, "1", "QTY", {"cart": {"UBE-01": "x" * 50}}).status_code == 422
    deep = '{"a": ' * 3000 + "{}" + "}" * 3000
    for context in (deep, '{"x": NaN}'):
        response = client.post(
            "/admin/workspace/test-chat",
            content='{"state": "IDLE", "value": "hi", "context": ' + context + "}",
            headers={**AUTH, "Content-Type": "application/json"},
        )
        # A clean client error, never a 500 from the process that also takes webhooks.
        assert 400 <= response.status_code < 500
