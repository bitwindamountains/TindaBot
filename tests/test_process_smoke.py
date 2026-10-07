import os
import socket
import subprocess
import sys
import time

import httpx
from conftest import envelope, signed
from sqlalchemy import func, select

from tindabot.db import Inbox, Outbox


def test_http_intake_survives_worker_absence_and_process_restart(db, settings):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update(
        APP_ENV="test",
        DATABASE_URL=settings.database_url.get_secret_value(),
        META_APP_SECRET=settings.meta_app_secret.get_secret_value(),
        META_PAGE_ID="100",
        DELIVERY_MODE="dry_run",
        WORKER_POLL_SECONDS="0.1",
    )
    kwargs = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    processes = []

    def wait_until(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        raise AssertionError("Process smoke check timed out")

    def ready():
        try:
            return httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    def completed():
        with db.sessions() as session:
            event = session.scalar(select(Inbox))
            job = session.scalar(select(Outbox))
            return bool(event and event.status == "done" and job and job.status == "dry_run")

    try:
        api = subprocess.Popen(
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
        processes.append(api)
        wait_until(ready)
        body, headers = signed(envelope("hi", mid="process-restart"))
        assert (
            httpx.post(
                f"http://127.0.0.1:{port}/webhook", content=body, headers=headers, timeout=5
            ).status_code
            == 200
        )
        with db.sessions() as session:
            assert session.scalar(select(Inbox)).status == "pending"
        worker = subprocess.Popen([sys.executable, "-m", "tindabot.worker"], **kwargs)
        processes.append(worker)
        wait_until(completed)
        worker.terminate()
        worker.wait(timeout=5)
        # Redelivery across a new worker process cannot repeat the committed effect.
        assert (
            httpx.post(
                f"http://127.0.0.1:{port}/webhook", content=body, headers=headers, timeout=5
            ).status_code
            == 200
        )
        processes.append(subprocess.Popen([sys.executable, "-m", "tindabot.worker"], **kwargs))
        wait_until(completed)
        with db.sessions() as session:
            assert session.scalar(select(func.count()).select_from(Inbox)) == 1
            assert session.scalar(select(func.count()).select_from(Outbox)) == 1
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
