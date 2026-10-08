import time

import pytest
from conftest import envelope, send
from sqlalchemy import func, select

from tindabot.db import Conversation, Inbox, Outbox, Record
from tindabot.events import accept_events
from tindabot.handover import set_pause
from tindabot.privacy import erase_customer
from tindabot.service import process_one
from tindabot.worker import maintenance

AUTH = {"Authorization": "Bearer " + "a" * 40}
PATH = "/admin/workspace/handovers"


def test_handover_operator_only_resume_checks_latest_message_and_sends_nothing(
    client, db, settings
):
    send(db, settings, "SELLER")
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers={"Authorization": "Bearer " + "b" * 40}).status_code == 401
    response = client.get(PATH, headers=AUTH)
    assert response.headers["cache-control"] == "no-store"
    c = response.json()["conversations"][0]
    assert c["reason"] == "customer"
    assert client.get("/admin/workspace", headers=AUTH).json()["handover_count"] == 1
    send(db, settings, "another private message")
    resume = "/admin/conversations/200/pause"
    body = {"enabled": False, "expected_version": c["version"]}
    assert client.post(resume, json=body, headers=AUTH).status_code == 409
    assert client.post(resume, json=body).status_code == 401
    latest = client.get(PATH, headers=AUTH)
    assert "another private message" not in latest.text
    c = latest.json()["conversations"][0]
    with db.sessions() as session:
        count = session.scalar(select(func.count()).select_from(Outbox))
    assert (
        client.post(
            resume, json={**body, "expected_version": c["version"]}, headers=AUTH
        ).status_code
        == 200
    )
    assert client.get(PATH, headers=AUTH).json()["conversations"] == []
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Outbox)) == count


def test_handover_survives_draft_expiry_but_erasure_clears_it(client, db, settings):
    send(db, settings, "SELLER")
    with db.sessions.begin() as session:
        c = session.get(Conversation, "100:200")
        c.context = {
            **c.context,
            "name": "Private draft name",
            "draft_created_at": time.time() - 90000,
        }
    maintenance(db, settings)
    c = client.get(PATH, headers=AUTH).json()["conversations"][0]
    assert c["name"] == "Customer"
    with db.sessions.begin() as session:
        erase_customer(session, "100:200")
    assert client.get(PATH, headers=AUTH).json()["conversations"] == []
    assert (
        client.post(
            "/admin/conversations/200/pause",
            headers=AUTH,
            json={"enabled": False, "expected_version": c["version"]},
        ).status_code
        == 409
    )


def test_page_echo_stop_and_customer_menu_update_handover(client, db, settings):
    send(db, settings, "hi")
    accept_events(db, settings, envelope("Seller reply", echo=True, app_id="external"))
    assert process_one(db, settings)
    assert client.get(PATH, headers=AUTH).json()["conversations"][0]["reason"] == "page_reply"
    send(db, settings, "STOP")
    assert client.get(PATH, headers=AUTH).json()["conversations"][0]["reason"] == "stop"
    send(db, settings, "MENU")
    assert client.get(PATH, headers=AUTH).json()["conversations"] == []


def test_handover_is_bounded_and_page_scoped(client, db):
    with db.sessions.begin() as session:
        for n in range(53):
            c = Conversation(key=f"100:{1000 + n}", psid=str(1000 + n), context={}, version=0)
            set_pause(c, True, now=time.time())
            session.add(c)
        other = Conversation(key="999:999", psid="999", context={}, version=0)
        set_pause(other, True)
        session.add(other)
    first = client.get(PATH, headers=AUTH).json()
    assert len(first["conversations"]) == 50
    second = client.get(PATH, params={"after": first["next_cursor"]}, headers=AUTH).json()
    assert len(second["conversations"]) == 3 and second["next_cursor"] is None
    assert client.get("/admin/workspace", headers=AUTH).json()["handover_count"] == 53


def test_requests_are_visible_while_global_automation_is_off(client, db, settings):
    with db.sessions.begin() as session:
        session.add(Record(key="automation", value={"enabled": False}))
    send(db, settings, "SELLER")
    c = client.get(PATH, headers=AUTH).json()["conversations"][0]
    assert c["reason"] == "customer"
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0


def test_stop_reason_survives_page_reply_and_repeated_pause(client, db, settings):
    send(db, settings, "STOP")
    initial = client.get(PATH, headers=AUTH).json()["conversations"][0]
    accept_events(db, settings, envelope("Seller reply", echo=True, app_id="external"))
    assert process_one(db, settings)
    assert (
        client.post(
            "/admin/conversations/200/pause", headers=AUTH, json={"enabled": True}
        ).status_code
        == 200
    )
    send(db, settings, "SELLER")
    current = client.get(PATH, headers=AUTH).json()["conversations"][0]
    assert current["reason"] == "stop"
    assert current["since"] == initial["since"]
    assert current["version"] > initial["version"]
    send(db, settings, "MENU")
    send(db, settings, "SELLER")
    assert client.get(PATH, headers=AUTH).json()["conversations"][0]["reason"] == "customer"


@pytest.mark.parametrize("kind", ["message", "echo", "failed"])
def test_resume_rejects_received_but_unprocessed_activity(client, db, settings, kind):
    send(db, settings, "SELLER")
    c = client.get(PATH, headers=AUTH).json()["conversations"][0]
    accept_events(
        db, settings, envelope("I still need help", echo=kind == "echo", app_id="external")
    )
    if kind == "failed":
        with db.sessions.begin() as session:
            session.scalar(select(Inbox).where(Inbox.status == "pending")).status = "failed"
    response = client.post(
        "/admin/conversations/200/pause",
        headers=AUTH,
        json={"enabled": False, "expected_version": c["version"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "conversation_pending"
    with db.sessions() as session:
        stored = session.get(Conversation, "100:200")
        assert stored.paused and stored.version == c["version"]
    if kind != "failed":
        assert process_one(db, settings)
        latest = client.get(PATH, headers=AUTH).json()["conversations"][0]
        assert (
            client.post(
                "/admin/conversations/200/pause",
                headers=AUTH,
                json={"enabled": False, "expected_version": latest["version"]},
            ).status_code
            == 200
        )
