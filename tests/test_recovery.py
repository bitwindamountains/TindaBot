from sqlalchemy import select

from tindabot.db import Outbox, Record

AUTH = {"Authorization": "Bearer " + "a" * 40}


def seed(db, count=1):
    with db.sessions.begin() as session:
        for n in range(count):
            session.add(
                Outbox(
                    business_key=f"recovery-{n}",
                    lane="email",
                    destination="email",
                    status="uncertain",
                    attempts=3,
                    payload={"secret": "private"},
                    error="private@example.com token=secret",
                )
            )


def test_inspection_is_private_bounded_and_redacted(client, db):
    seed(db, 53)
    path = "/admin/workspace/jobs"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer " + "b" * 40}).status_code == 401
    first = client.get(path, headers=AUTH)
    assert first.headers["cache-control"] == "no-store"
    assert "private" not in first.text and "secret" not in first.text
    assert len(first.json()["jobs"]) == 50
    second = client.get(path, params={"before": first.json()["next_cursor"]}, headers=AUTH).json()
    assert len(second["jobs"]) == 3
    assert second["next_cursor"] is None
    assert client.get(path + "?status=failed", headers=AUTH).json()["jobs"] == []
    assert client.get(path + "?before=0", headers=AUTH).status_code == 422


def test_recovery_acknowledgement_idempotency_and_audit(client, db):
    seed(db)
    job = client.get("/admin/workspace/jobs", headers=AUTH).json()["jobs"][0]
    path = f"/admin/jobs/{job['id']}/resolve"
    body = {"action": "retry", "command_id": "retry-one", "expected_revision": job["revision"]}
    assert client.post(path, json=body).status_code == 401
    assert (
        client.post(path, json=body, headers={"Authorization": "Bearer " + "b" * 40}).status_code
        == 401
    )
    assert client.post(path, json=body, headers=AUTH).status_code == 409
    body["accept_duplicate_risk"] = True
    assert client.post(path, json=body, headers=AUTH).status_code == 200
    # Even if the worker fails again, a lost-response retry must not resolve it again.
    with db.sessions.begin() as session:
        row = session.get(Outbox, job["id"])
        row.status, row.attempts, row.next_attempt = "failed", 4, 1234
    assert client.post(path, json=body, headers=AUTH).status_code == 200
    with db.sessions() as session:
        assert session.get(Outbox, job["id"]).status == "failed"
        audits = session.scalars(select(Record).where(Record.key.like("audit:%"))).all()
        assert len(audits) == 1
        assert audits[0].value["accept_duplicate_risk"] is True
        assert audits[0].value["attempts"] == 3
    assert client.post(path, json={**body, "action": "suppress"}, headers=AUTH).status_code == 409
    assert client.post(path, json={**body, "command_id": "stale"}, headers=AUTH).status_code == 409
    current = client.get("/admin/workspace/jobs", headers=AUTH).json()["jobs"][0]
    assert (
        client.post(
            path,
            json={
                **body,
                "command_id": "suppress",
                "action": "suppress",
                "expected_revision": current["revision"],
            },
            headers=AUTH,
        ).status_code
        == 200
    )
    assert client.get("/admin/workspace/jobs", headers=AUTH).json()["jobs"] == []
