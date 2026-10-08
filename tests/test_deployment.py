import signal
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from tindabot import worker
from tindabot.db import Record


@pytest.mark.parametrize("revision", ["0002", "9999", None])
def test_api_rejects_incompatible_or_unmigrated_schema(client, db, revision):
    with db.engine.begin() as connection:
        if revision is None:
            connection.execute(text("DROP TABLE alembic_version"))
        else:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": revision},
            )
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


@pytest.mark.parametrize("revision", ["0002", "9999", None])
def test_worker_waits_for_schema_before_heartbeat_and_processing(
    db, settings, monkeypatch, revision
):
    with db.engine.begin() as connection:
        if revision is None:
            connection.execute(text("DROP TABLE alembic_version"))
        else:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :revision"),
                {"revision": revision},
            )

    handlers = {}
    monkeypatch.setattr(
        worker.signal, "signal", lambda sig, handler: handlers.update({sig: handler})
    )
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "Database", lambda _: db)
    adapter = Mock()
    monkeypatch.setattr(worker, "Integrations", lambda _: adapter)
    process = Mock(side_effect=lambda *_: handlers[signal.SIGTERM]())
    dispatch, maintain, sync = Mock(return_value=False), Mock(), Mock()
    monkeypatch.setattr(worker, "process_one", process)
    monkeypatch.setattr(worker, "dispatch_one", dispatch)
    monkeypatch.setattr(worker, "maintenance", maintain)
    monkeypatch.setattr(worker, "sync_seller", sync)
    waits = []

    def migrate_after_wait(_):
        waits.append(True)
        if len(waits) > 1:
            handlers[signal.SIGTERM]()
            return
        process.assert_not_called()
        dispatch.assert_not_called()
        maintain.assert_not_called()
        sync.assert_not_called()
        with db.sessions() as session:
            assert session.get(Record, "worker-heartbeat") is None
        with db.engine.begin() as connection:
            if revision is None:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                connection.execute(text("INSERT INTO alembic_version VALUES ('0003')"))
            else:
                connection.execute(text("UPDATE alembic_version SET version_num = '0003'"))

    monkeypatch.setattr(worker.time, "sleep", migrate_after_wait)
    worker.run()
    process.assert_called_once()
    dispatch.assert_called_once()
    maintain.assert_called_once()
    sync.assert_called_once()
    adapter.close.assert_called_once()
    with db.sessions() as session:
        assert session.get(Record, "worker-heartbeat") is not None
