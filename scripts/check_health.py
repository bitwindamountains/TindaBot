"""Run from an external monitor; a nonzero exit should page the operator."""

import json
import os
import sys

import httpx


def main():
    base = os.environ["TINDABOT_URL"].rstrip("/")
    token = os.environ["ADMIN_TOKEN"]
    try:
        with httpx.Client(timeout=10) as client:
            client.get(base + "/readyz").raise_for_status()
            response = client.get(
                base + "/admin/health", headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            health = response.json()
        failed = (
            health["worker_age_seconds"] is None
            or health["worker_age_seconds"] > 60
            or health["oldest_event_age_seconds"] > 30
            or health["inbox_failed"] > 0
            or health["outbox"].get("failed", 0) > 0
            or health["outbox"].get("uncertain", 0) > 0
            or (health["seller_sync"] is not None and not health["seller_sync"].get("ok"))
        )
        print(json.dumps({"healthy": not failed, "checks": health}))
        sys.exit(1 if failed else 0)
    except (httpx.HTTPError, ValueError, KeyError):
        print(json.dumps({"healthy": False, "error": "health_check_failed"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
