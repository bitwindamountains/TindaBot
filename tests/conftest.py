import hashlib
import hmac
import json
import time
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tindabot.catalog import CatalogImport, import_catalog
from tindabot.cli import DEMO
from tindabot.config import Settings
from tindabot.db import Database
from tindabot.events import accept_events
from tindabot.main import create_app
from tindabot.service import process_one


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        meta_app_secret="s" * 32,
        meta_verify_token="v" * 32,
        meta_page_id="100",
        meta_app_id="900",
        admin_token="a" * 40,
        status_token="b" * 40,
        max_messages_per_minute=1000,
    )


@pytest.fixture
def db(settings, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", settings.database_url.get_secret_value())
    monkeypatch.setenv("APP_ENV", "test")
    command.upgrade(Config("alembic.ini"), "head")
    database = Database(settings)
    with database.sessions.begin() as session:
        import_catalog(session, CatalogImport(**DEMO))
    yield database
    database.engine.dispose()


@pytest.fixture
def client(settings, db):
    with TestClient(create_app(settings, db)) as client:
        yield client


def envelope(
    value="hi", *, psid="200", mid=None, now=None, echo=False, app_id=None, postback=False
):
    event = {
        "sender": {"id": "100" if echo else psid},
        "recipient": {"id": psid if echo else "100"},
        "timestamp": int((now or time.time()) * 1000),
    }
    if postback:
        event["postback"] = {"payload": value}
        if mid:
            event["postback"]["mid"] = mid
    else:
        event["message"] = {"text": value, "mid": mid or str(uuid.uuid4())}
        if echo:
            event["message"]["is_echo"] = True
        if app_id:
            event["message"]["app_id"] = app_id
    return {"object": "page", "entry": [{"id": "100", "messaging": [event]}]}


def signed(document, secret="s" * 32):
    body = json.dumps(document).encode()
    return body, {
        "x-hub-signature-256": "sha256="
        + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    }


def send(db, settings, value, psid="200", now=None):
    accept_events(db, settings, envelope(value, psid=psid, now=now))
    assert process_one(db, settings, now=now)


def checkout(db, settings, psid="200", sku="UBE-01", qty=1):
    for value in [
        "SHOP",
        f"PRODUCT:{sku}",
        f"QTY:{qty}",
        "CHECKOUT",
        "DELIVERY:delivery",
        "Juan Dela Cruz",
        "09171234567",
        "123 Mabini Street, Quezon City",
        "PAY:cod",
    ]:
        send(db, settings, value, psid)
    from tindabot.db import Conversation

    with db.sessions() as session:
        ctx = session.get(Conversation, f"100:{psid}").context
    return f"CONFIRM:{ctx['checkout_id']}:{ctx['version']}"
