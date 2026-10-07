import json

import pytest
from conftest import envelope, signed
from sqlalchemy import func, select

from tindabot.db import Inbox
from tindabot.events import parse_events


def test_health_and_verification(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert (
        client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "v" * 32,
                "hub.challenge": "12345",
            },
        ).text
        == "12345"
    )
    assert client.get("/webhook", params={"hub.verify_token": "bad"}).status_code == 403


def test_signed_intake_is_durable_and_deduplicated(client, db):
    body, headers = signed(envelope(mid="same-message"))
    assert client.post("/webhook", content=body, headers=headers).status_code == 200
    assert client.post("/webhook", content=body, headers=headers).status_code == 200
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Inbox)) == 1
        assert session.scalar(select(Inbox)).status == "pending"


def test_invalid_and_modified_signatures_rejected(client, db):
    body, headers = signed(envelope())
    assert client.post("/webhook", content=body).status_code == 403
    assert client.post("/webhook", content=body + b" ", headers=headers).status_code == 403
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Inbox)) == 0


def test_wrong_page_and_malformed_batch_are_atomic(client, db):
    document = envelope()
    document["entry"].append({"id": "wrong", "messaging": []})
    body, headers = signed(document)
    assert client.post("/webhook", content=body, headers=headers).status_code == 400
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Inbox)) == 0


def test_postback_without_mid_has_stable_non_null_identity():
    doc = envelope("SHOP", now=1000, postback=True)
    first = parse_events(doc, "100", 1001)
    assert first == parse_events(json.loads(json.dumps(doc)), "100", 1001)
    assert first[0]["event_key"]


@pytest.mark.parametrize(
    "document", [[], {}, {"object": "user"}, {"object": "page", "entry": [None]}]
)
def test_malformed_envelopes(client, document):
    body, headers = signed(document)
    assert client.post("/webhook", content=body, headers=headers).status_code == 400


def test_database_failure_does_not_acknowledge(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    import tindabot.main

    def fail(*args):
        raise OperationalError("unavailable", {}, Exception())

    monkeypatch.setattr(tindabot.main, "accept_events", fail)
    body, headers = signed(envelope())
    assert client.post("/webhook", content=body, headers=headers).status_code == 503


def test_body_limit(client, settings):
    assert client.post("/webhook", content=b"x" * (settings.max_body_bytes + 1)).status_code == 413


def test_scoped_admin_credentials(client):
    assert client.get("/admin/health").status_code == 401
    assert (
        client.get("/admin/health", headers={"Authorization": "Bearer " + "b" * 40}).status_code
        == 401
    )
    assert (
        client.get("/admin/health", headers={"Authorization": "Bearer " + "a" * 40}).status_code
        == 200
    )
