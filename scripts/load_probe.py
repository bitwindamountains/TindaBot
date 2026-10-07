"""Paced localhost API/worker soak against an explicitly disposable PostgreSQL DB.

Never sends to Meta, Sheets or SMTP. LOAD_DATABASE_URL must identify an empty
database ending in _test. Example: --seconds 600 --rate 10 --output report.json.
"""

import argparse
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--rate", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("LOAD_DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
        parser.error("Use LOAD_DATABASE_URL for an empty PostgreSQL database ending in _test")
    if not 1 <= args.seconds <= 3600 or not 1 <= args.rate <= 100:
        parser.error("Probe bounds: 1–3600 seconds and 1–100 events/second")
    engine = create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    with engine.connect() as connection:
        if connection.scalar(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        ):
            parser.error("Refusing to run against a non-empty database")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    secret = os.urandom(32).hex()
    env = os.environ.copy()
    env.update(
        APP_ENV="test",
        DATABASE_URL=url,
        DELIVERY_MODE="dry_run",
        META_PAGE_ID="100",
        META_APP_SECRET=secret,
        WORKER_POLL_SECONDS="0.1",
        MAX_MESSAGES_PER_MINUTE="1000",
    )
    kwargs = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, **kwargs)
    subprocess.run([sys.executable, "-m", "tindabot.cli", "seed-demo"], check=True, **kwargs)
    processes, latencies, observed_lag, errors = [], [], [], []
    try:
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tindabot.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                **kwargs,
            )
        )
        processes.append(subprocess.Popen([sys.executable, "-m", "tindabot.worker"], **kwargs))
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=5) as client:
            for _ in range(150):
                try:
                    if client.get(base + "/readyz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("API startup timed out")
            start = time.monotonic()
            for index in range(args.seconds * args.rate):
                due = start + index / args.rate
                if due > time.monotonic():
                    time.sleep(due - time.monotonic())
                document = {
                    "object": "page",
                    "entry": [
                        {
                            "id": "100",
                            "messaging": [
                                {
                                    "sender": {"id": str(1000 + index % 500)},
                                    "recipient": {"id": "100"},
                                    "timestamp": int(time.time() * 1000),
                                    "message": {"mid": f"probe-{index}", "text": "hi"},
                                }
                            ],
                        }
                    ],
                }
                body = json.dumps(document).encode()
                signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                before = time.monotonic()
                try:
                    response = client.post(
                        base + "/webhook", content=body, headers={"x-hub-signature-256": signature}
                    )
                    if response.status_code != 200:
                        errors.append({"index": index, "status": response.status_code})
                except httpx.HTTPError as exc:
                    errors.append({"index": index, "error": type(exc).__name__})
                latencies.append(time.monotonic() - before)
                if index % (args.rate * 10) == 0:
                    with engine.connect() as connection:
                        oldest = connection.scalar(
                            text(
                                "SELECT min(received_at) FROM inbound_events WHERE status='pending'"
                            )
                        )
                        observed_lag.append(max(0, time.time() - oldest) if oldest else 0)
            for _ in range(300):
                with engine.connect() as connection:
                    pending = connection.scalar(
                        text("SELECT count(*) FROM inbound_events WHERE status!='done'")
                    )
                    jobs = connection.scalar(
                        text(
                            "SELECT count(*) FROM outbound_jobs WHERE status IN ('pending','processing')"
                        )
                    )
                if not pending and not jobs:
                    break
                time.sleep(0.1)
        with engine.connect() as connection:
            counts = {
                row[0]: row[1]
                for row in connection.execute(
                    text("SELECT status,count(*) FROM inbound_events GROUP BY status")
                )
            }
            deliveries = {
                row[0]: row[1]
                for row in connection.execute(
                    text("SELECT status,count(*) FROM outbound_jobs GROUP BY status")
                )
            }
        ordered = sorted(latencies)
        report = {
            "environment": "local PostgreSQL, localhost HTTP, dry-run providers",
            "target_rate_per_second": args.rate,
            "duration_seconds": args.seconds,
            "events_sent": len(latencies),
            "http_errors": errors,
            "ack_p95_seconds": ordered[int((len(ordered) - 1) * 0.95)],
            "ack_max_seconds": max(ordered),
            "sampled_max_inbox_age_seconds": max(observed_lag),
            "inbox_states": counts,
            "outbox_states": deliveries,
            "pass": not errors
            and counts.get("done") == len(latencies)
            and not pending
            and not jobs
            and ordered[int((len(ordered) - 1) * 0.95)] < 1,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        if not report["pass"]:
            raise SystemExit(1)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        engine.dispose()


if __name__ == "__main__":
    main()
