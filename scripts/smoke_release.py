"""Exercise an installed wheel, its web assets, and migrations without provider calls.

Run from the repository root using the isolated release environment's Python.
"""

import json
import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import tindabot
from tindabot.config import Settings
from tindabot.db import Conversation, Order
from tindabot.main import create_app


def main():
    package = Path(tindabot.__file__).resolve()
    if "site-packages" not in package.parts:
        raise SystemExit(
            "Use an isolated environment with the built wheel installed, not editable source"
        )
    with tempfile.TemporaryDirectory(prefix="tindabot-release-") as directory:
        url = f"sqlite:///{Path(directory).as_posix()}/release.db"
        # Keep this independent of any user/provider .env configuration.
        os.environ.update(APP_ENV="test", DATABASE_URL=url, DELIVERY_MODE="dry_run")
        command.upgrade(Config("alembic.ini"), "head")
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url=url,
            delivery_mode="dry_run",
            admin_token="release-smoke-token-only",
        )
        with TestClient(create_app(settings)) as client:
            assert client.get("/healthz").json() == {"status": "ok"}
            assert client.get("/readyz").status_code == 200
            shell = client.get("/")
            assert shell.status_code == 200 and "TindaBot" in shell.text
            assert "frame-ancestors 'none'" in shell.headers["content-security-policy"]
            assets = [
                "studio.css",
                "motion.js",
                "tokens.css",
                "workspace.css",
                "theme.js",
                "app.js",
                "icons.js",
                "demo.js",
                "favicon.svg",
                "effects/hero.js",
                "effects/hero.js.LEGAL.txt",
                "effects/THIRD_PARTY_NOTICES.txt",
            ]
            for asset in assets:
                response = client.get(f"/assets/{asset}")
                assert response.status_code == 200 and len(response.content) > 50, asset
            assert client.get("/admin/workspace").status_code == 401
            snapshot = client.get(
                "/admin/workspace", headers={"Authorization": "Bearer release-smoke-token-only"}
            )
            assert snapshot.status_code == 200
            assert snapshot.json()["summary"]["orders"] == 0
            assert snapshot.json()["job_health"] == {
                "inbox_failed": 0,
                "delivery_failed": 0,
                "delivery_uncertain": 0,
            }
            assert snapshot.headers["cache-control"] == "no-store"
            queue = client.get(
                "/admin/workspace?scope=open&sort=oldest",
                headers={"Authorization": "Bearer release-smoke-token-only"},
            )
            assert queue.status_code == 200
            assert queue.json()["order_total"] == 0
            assert queue.json()["next_cursor"] is None
            with client.app.state.db.sessions.begin() as session:
                session.add(Conversation(key="smoke:customer", psid="smoke-customer"))
                session.flush()
                session.add(
                    Order(
                        id="smoke-order",
                        code="TB-SMOKE",
                        checkout_id="smoke-checkout",
                        conversation_key="smoke:customer",
                        details={"payment": "gcash"},
                        items=[],
                        total_minor=10000,
                        shipping_minor=0,
                        status="cancelled",
                        payment_status="refund_required",
                    )
                )
            auth = {"Authorization": "Bearer release-smoke-token-only"}
            assert (
                client.post(
                    "/admin/orders/smoke-order/notes",
                    headers=auth,
                    json={
                        "command_id": "smoke-note",
                        "expected_version": 1,
                        "body": "Release fixture note",
                    },
                ).status_code
                == 200
            )
            refund = client.post(
                "/admin/orders/smoke-order/refunds",
                headers=auth,
                json={
                    "command_id": "smoke-refund",
                    "expected_version": 2,
                    "amount_minor": 10000,
                    "reference": "SMOKE-ONLY",
                },
            )
            assert refund.status_code == 200 and refund.json()["payment_status"] == "refunded"
            detail = client.get("/admin/workspace/orders/smoke-order", headers=auth).json()
            assert detail["refunded_minor"] == 10000
            assert [event["kind"] for event in detail["activity"]] == ["refund", "note"]
    report = {
        "installed_wheel": True,
        "migrations": "0003",
        "web_assets_verified": assets,
        "public_shell": True,
        "authenticated_snapshot": True,
        "diagnostic_contract_verified": True,
        "all_time_queue_contract_verified": True,
        "notes_refund_and_activity_verified": True,
        "providers_called": False,
        "scope": "Installed wheel and migrations in isolated local Python environment; not container or hosting validation",
    }
    Path("docs/validation/release-smoke.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("PASS: installed wheel, migrations, web assets, readiness, and authenticated snapshot")


if __name__ == "__main__":
    main()
