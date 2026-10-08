import hmac
import json
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from tindabot.catalog import CatalogImport, adjust_stock, import_catalog
from tindabot.config import Settings
from tindabot.db import Conversation, Database, Inbox, Outbox, Record, insert_once
from tindabot.events import accept_events, valid_signature
from tindabot.handover import set_pause
from tindabot.orders import OrderConflict, apply_order_action, change_status
from tindabot.recovery import revision


class StatusCommand(BaseModel):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    order_id: str = Field(max_length=36)
    expected_version: int = Field(ge=1)
    status: str = Field(pattern=r"^(pending|confirmed|paid|shipped|delivered|cancelled)$")


class StockCommand(BaseModel):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    sku: str = Field(max_length=64)
    delta: int = Field(ge=-1_000_000, le=1_000_000)


class NoteCommand(BaseModel):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    expected_version: int = Field(ge=1)
    body: str = Field(min_length=1, max_length=2000)


class RefundCommand(BaseModel):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    expected_version: int = Field(ge=1)
    amount_minor: int = Field(strict=True, ge=1, le=2_000_000_000)
    reference: str = Field(default="", max_length=160)
    completed_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Toggle(BaseModel):
    enabled: bool


class PauseCommand(Toggle):
    expected_version: int | None = Field(default=None, ge=0)


class Replay(BaseModel):
    action: str = Field(pattern=r"^(retry|suppress)$")
    accept_duplicate_risk: bool = False
    command_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,80}$")
    expected_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def create_app(settings=None, database=None):
    from tindabot.logging_setup import configure_logging

    configure_logging()
    settings = settings or Settings()
    db = database or Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if database is None:
            db.engine.dispose()

    app = FastAPI(
        title="TindaBot",
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.db, app.state.settings = db, settings

    def token_matches(header, token):
        expected = token.get_secret_value()
        return bool(expected) and hmac.compare_digest(
            header.encode(), ("Bearer " + expected).encode()
        )

    def operator(authorization: str = Header(default="")):
        if not token_matches(authorization, settings.admin_token):
            raise HTTPException(401, "Unauthorized")

    def status_auth(authorization: str = Header(default="")):
        if not (
            token_matches(authorization, settings.status_token)
            or token_matches(authorization, settings.admin_token)
        ):
            raise HTTPException(401, "Unauthorized")

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            with db.sessions() as session:
                revision = session.scalar(text("SELECT version_num FROM alembic_version"))
                session.scalar(select(Inbox.id).limit(1))
                if revision != "0003":
                    raise HTTPException(503, "Schema not ready")
            return {"status": "ready"}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Database not ready") from exc

    @app.get("/webhook", response_class=PlainTextResponse)
    def verify(request: Request):
        q = request.query_params
        token = settings.meta_verify_token.get_secret_value()
        if (
            q.get("hub.mode") != "subscribe"
            or not token
            or not hmac.compare_digest(q.get("hub.verify_token", "").encode(), token.encode())
        ):
            raise HTTPException(403, "Verification failed")
        challenge = q.get("hub.challenge", "")
        if not challenge or len(challenge) > 200:
            raise HTTPException(400, "Invalid challenge")
        return challenge

    @app.post("/webhook", response_class=PlainTextResponse)
    async def webhook(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > settings.max_body_bytes:
                raise HTTPException(413, "Payload too large")
        if not valid_signature(
            bytes(body),
            request.headers.get("x-hub-signature-256", ""),
            settings.meta_app_secret.get_secret_value(),
        ):
            raise HTTPException(403, "Invalid signature")
        try:
            document = json.loads(body)
            await run_in_threadpool(accept_events, db, settings, document)
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
            raise HTTPException(400, "Invalid event envelope") from exc
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Durable intake unavailable") from exc
        return "EVENT_RECEIVED"

    @app.get("/admin/health", dependencies=[Depends(operator)])
    def operational_health():
        with db.sessions() as session:
            heartbeat = session.get(Record, "worker-heartbeat")
            oldest = session.scalar(
                select(func.min(Inbox.received_at)).where(Inbox.status == "pending")
            )
            states = dict(
                session.execute(select(Outbox.status, func.count()).group_by(Outbox.status)).all()
            )
            failures = session.scalar(
                select(func.count()).select_from(Inbox).where(Inbox.status == "failed")
            )
            sync = session.get(Record, "seller-sync")
            return {
                "worker_age_seconds": time.time() - heartbeat.updated_at if heartbeat else None,
                "oldest_event_age_seconds": time.time() - oldest if oldest else 0,
                "inbox_failed": failures,
                "outbox": states,
                "seller_sync": sync.value if sync else None,
            }

    @app.post("/admin/catalog", dependencies=[Depends(operator)])
    def catalog(document: CatalogImport):
        try:
            with db.sessions.begin() as session:
                import_catalog(session, document)
            return {"success": True}
        except ValueError as exc:
            raise HTTPException(422, "Invalid catalog") from exc

    @app.post("/admin/stock", dependencies=[Depends(operator)])
    def stock(command: StockCommand):
        try:
            with db.sessions.begin() as session:
                return adjust_stock(session, command.sku, command.delta, command.command_id)
        except OrderConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/admin/order-status", dependencies=[Depends(status_auth)])
    def status(command: StatusCommand):
        try:
            with db.sessions.begin() as session:
                return change_status(
                    session,
                    command.order_id,
                    command.expected_version,
                    command.status,
                    command.command_id,
                )
        except OrderConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/admin/orders/{order_id}/notes", dependencies=[Depends(operator)])
    def add_note(order_id: str, command: NoteCommand):
        try:
            with db.sessions.begin() as session:
                return apply_order_action(
                    session,
                    order_id,
                    command.expected_version,
                    command.command_id,
                    "note",
                    command.body,
                )
        except OrderConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/admin/orders/{order_id}/refunds", dependencies=[Depends(operator)])
    def record_refund(order_id: str, command: RefundCommand):
        try:
            with db.sessions.begin() as session:
                return apply_order_action(
                    session,
                    order_id,
                    command.expected_version,
                    command.command_id,
                    "refund",
                    command.reference,
                    amount_minor=command.amount_minor,
                    occurred_at=command.completed_at,
                )
        except OrderConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/admin/automation", dependencies=[Depends(operator)])
    def automation(command: Toggle):
        with db.sessions.begin() as session:
            insert_once(session, Record, {"key": "automation", "value": {}}, "key")
            control = session.scalar(
                select(Record).where(Record.key == "automation").with_for_update()
            )
            control.value = {"enabled": command.enabled}
        return {"enabled": command.enabled}

    @app.post("/admin/conversations/{psid}/pause", dependencies=[Depends(operator)])
    def pause(psid: str, command: PauseCommand):
        with db.sessions.begin() as session:
            conversation = session.scalar(
                select(Conversation)
                .where(Conversation.key == f"{settings.meta_page_id}:{psid}")
                .with_for_update()
            )
            if not conversation:
                raise HTTPException(404, "Conversation not found")
            # Version changes happen during processing, not durable intake. Do not
            # resume past customer activity that the operator has not seen yet.
            if not command.enabled and session.scalar(
                select(Inbox.id)
                .where(
                    Inbox.conversation_key == conversation.key,
                    Inbox.status.in_(["pending", "failed"]),
                )
                .limit(1)
            ):
                raise HTTPException(409, "conversation_pending")
            if (
                command.expected_version is not None
                and command.expected_version != conversation.version
            ):
                raise HTTPException(409, "Conversation changed; refresh the handover queue")
            set_pause(conversation, command.enabled, now=time.time())
        return {"paused": command.enabled}

    @app.post("/admin/jobs/{job_id}/resolve", dependencies=[Depends(operator)])
    def resolve(job_id: int, command: Replay):
        with db.sessions.begin() as session:
            receipt = None
            fingerprint = {"job_id": job_id, **command.model_dump(exclude={"command_id"})}
            if command.command_id:
                key = f"recovery:{command.command_id}"
                if not insert_once(session, Record, {"key": key, "value": {}}, "key"):
                    receipt = session.get(Record, key)
                    if receipt.value.get("request") != fingerprint:
                        raise HTTPException(409, "Recovery command was already used")
                    return receipt.value["result"]
                receipt = session.get(Record, key)
            job = session.scalar(select(Outbox).where(Outbox.id == job_id).with_for_update())
            if not job or job.status not in {"failed", "uncertain"}:
                raise HTTPException(409, "Job is not awaiting resolution")
            if command.expected_revision and command.expected_revision != revision(job):
                raise HTTPException(409, "Job changed; refresh delivery review")
            if (
                command.action == "retry"
                and job.status == "uncertain"
                and not command.accept_duplicate_risk
            ):
                raise HTTPException(
                    409, "Reconcile the external result before accepting duplicate risk"
                )
            session.add(
                Record(
                    key=f"audit:{time.time_ns()}",
                    value={
                        "job_id": job_id,
                        "action": command.action,
                        "prior": job.status,
                        "actor": "operator",
                        "attempts": job.attempts,
                        "accept_duplicate_risk": command.accept_duplicate_risk,
                    },
                )
            )
            job.status = "pending" if command.action == "retry" else "suppressed"
            job.attempts, job.next_attempt, job.error = 0, 0, None
            if receipt:
                receipt.value = {"request": fingerprint, "result": {"success": True}}
        return {"success": True}

    @app.post("/admin/conversations/{psid}/erase", dependencies=[Depends(operator)])
    def erase(psid: str):
        from tindabot.privacy import erase_customer

        try:
            with db.sessions.begin() as session:
                return erase_customer(session, f"{settings.meta_page_id}:{psid}")
        except ValueError as exc:
            raise HTTPException(409, "Resolve in-flight delivery before erasure") from exc

    from tindabot.workspace import register_workspace

    register_workspace(app, db, settings, operator)
    return app
