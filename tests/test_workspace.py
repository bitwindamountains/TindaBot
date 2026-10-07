import time

from conftest import checkout, send

from tindabot.db import Inbox, Order, Outbox, Record

AUTH = {"Authorization": "Bearer " + "a" * 40}


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
