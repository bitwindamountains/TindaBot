import logging
import random
import signal
import time
import uuid

from sqlalchemy import exists, select, update
from sqlalchemy.orm import aliased

from tindabot.catalog import import_catalog
from tindabot.config import Settings
from tindabot.db import (
    Conversation,
    Database,
    Inbox,
    Order,
    OrderActivity,
    Outbox,
    Record,
    enqueue,
    insert_once,
)
from tindabot.integrations import DeliveryError, Integrations
from tindabot.orders import OrderConflict, change_status, record_activity
from tindabot.service import process_one

log = logging.getLogger("tindabot")


def claim_job(db, now):
    with db.sessions.begin() as session:
        # An abandoned external write cannot be assumed not to have happened.
        expired = session.scalars(
            select(Outbox)
            .where(Outbox.status == "processing", Outbox.lease_until < now)
            .with_for_update(skip_locked=True)
        ).all()
        for job in expired:
            job.status = "pending" if job.destination == "sheets" else "uncertain"
            job.error = "lease_expired"
        session.flush()
        prior = aliased(Outbox)
        blocked = exists(
            select(prior.id).where(
                prior.lane == Outbox.lane,
                prior.id < Outbox.id,
                prior.status.in_(["pending", "processing", "uncertain", "failed"]),
            )
        )
        job = session.scalar(
            select(Outbox)
            .where(Outbox.status == "pending", Outbox.next_attempt <= now, ~blocked)
            .order_by(Outbox.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        job.status = "processing"
        job.lease_token = str(uuid.uuid4())
        # Each provider request is bounded to 15 seconds; export uses up to three calls.
        job.lease_until = now + 120
        job.attempts += 1
        session.flush()
        return job


def dispatch_one(db, settings, integrations, now=None):
    now = now or time.time()
    job = claim_job(db, now)
    if not job:
        return False
    outcome, error, sent_mid = "delivered", None, None
    outbound_action = None
    try:
        with db.sessions() as session:
            conversation = (
                session.get(Conversation, job.conversation_key) if job.conversation_key else None
            )
            order = session.get(Order, job.order_id) if job.order_id else None
            if job.destination == "messenger":
                control = session.get(Record, "automation")
                enabled = settings.automation_enabled and (
                    not control or control.value.get("enabled", True)
                )
                expired = (
                    not conversation
                    or now - conversation.last_customer_at >= 86400
                    or now - job.payload.get("event_at", 0) >= 86400
                )
                superseded = (
                    conversation
                    and conversation.version
                    > job.payload.get("conversation_version", conversation.version)
                    and not job.payload.get("receipt")
                )
                if (
                    expired
                    or superseded
                    or not enabled
                    or (conversation.paused and not job.payload.get("allow_paused"))
                ):
                    outcome = "suppressed"
                # Never dispatch a reply while an already accepted seller echo or newer
                # control event remains to be processed for that conversation.
                elif session.scalar(
                    select(Inbox.id)
                    .where(
                        Inbox.conversation_key == conversation.key,
                        Inbox.status.in_(["pending", "failed"]),
                    )
                    .limit(1)
                ):
                    outcome = "pending"
                elif settings.delivery_mode == "dry_run":
                    outcome = "dry_run"
                else:
                    outbound_action = ("messenger", conversation.psid, job.payload["message"])
            elif settings.delivery_mode == "dry_run":
                outcome = "dry_run"
            elif job.destination == "sheets" and order:
                outbound_action = ("sheets", order)
            elif job.destination == "email":
                outbound_action = ("email", order, job.payload.get("handover", False))
            else:
                raise DeliveryError("missing_delivery_target")
        # Release the read transaction and pooled connection before network I/O.
        # The persistent job lease owns delivery; business rows are not locked here.
        if outbound_action:
            if outbound_action[0] == "messenger":
                sent_mid = integrations.send_message(*outbound_action[1:])
            elif outbound_action[0] == "sheets":
                integrations.export_order(outbound_action[1])
            else:
                integrations.send_email(*outbound_action[1:])
    except DeliveryError as exc:
        outcome = "uncertain" if exc.uncertain else "pending" if exc.retry else "failed"
        error = exc.code
    except Exception as exc:
        # Sheets jobs reconcile by stable order ID before retry. Other unknown writes
        # are held for operator review rather than blindly duplicated.
        outcome = "pending" if job.destination == "sheets" else "uncertain"
        error = type(exc).__name__[:100]
    with db.sessions.begin() as session:
        current = session.scalar(select(Outbox).where(Outbox.id == job.id).with_for_update())
        if current.lease_token != job.lease_token or current.status != "processing":
            return True
        if outcome == "pending" and current.attempts >= settings.max_attempts and error:
            outcome = "failed"
        current.status, current.error = outcome, error
        current.next_attempt = now + min(300, 2 ** min(current.attempts, 8)) + random.random()
        current.lease_until = 0
        if sent_mid:
            insert_once(
                session, Record, {"key": f"sent:{sent_mid}", "value": {}, "updated_at": now}, "key"
            )
        if error == "meta_credentials":
            insert_once(session, Record, {"key": "automation", "value": {}}, "key")
            control = session.get(Record, "automation")
            control.value = {"enabled": False, "reason": "meta_credentials"}
    if outcome in {"failed", "uncertain"}:
        log.error("delivery_attention", extra={"job_id": job.id, "error_code": error})
    return True


def maintenance(db, settings, now=None):
    now = now or time.time()
    with db.sessions.begin() as session:
        insert_once(session, Record, {"key": "maintenance", "value": {}, "updated_at": 0}, "key")
        marker = session.scalar(
            select(Record).where(Record.key == "maintenance").with_for_update(skip_locked=True)
        )
        if not marker or now - marker.updated_at < 60:
            return
        marker.updated_at = now
        for order in session.scalars(
            select(Order)
            .where(
                Order.expires_at <= now,
                Order.payment_status == "unpaid",
                Order.status.in_(["pending", "confirmed"]),
            )
            .order_by(Order.id)
            .with_for_update()
        ):
            change_status(
                session,
                order.id,
                order.version,
                "cancelled",
                f"expiry-{order.id}",
                now,
                actor="system",
            )
        for conversation in session.scalars(
            select(Conversation)
            .where(
                (Conversation.updated_at < now - 86400)
                | (Conversation.context["draft_created_at"].as_float() < now - 86400)
            )
            .with_for_update(skip_locked=True)
        ):
            marker = conversation.context.get("handover")
            conversation.context = {"handover": marker} if marker and conversation.paused else {}
            conversation.state = "IDLE"
        cutoff = now - settings.order_pii_retention_days * 86400
        for order in session.scalars(
            select(Order)
            .where(Order.created_at < cutoff, Order.anonymized.is_(False))
            .with_for_update(skip_locked=True)
        ):
            order.details = {k: v for k, v in order.details.items() if k in {"delivery", "payment"}}
            order.anonymized = True
            order.version += 1
            session.execute(
                update(OrderActivity).where(OrderActivity.order_id == order.id).values(body=None)
            )
            record_activity(session, order, "retention", "system", now)
            enqueue(session, key=f"retention:{order.id}", destination="sheets", order=order.id)
        # Keep idempotency metadata; remove raw personal text independently.
        session.execute(
            update(Inbox)
            .where(
                Inbox.received_at < now - settings.event_retention_days * 86400,
                Inbox.status == "done",
            )
            .values(payload={})
        )
        # Expired blocked work must not retain checkout PII forever. Preserve event/job
        # identifiers for audit and deduplication, but make expired work non-replayable.
        session.execute(
            update(Inbox)
            .where(
                Inbox.received_at < now - settings.event_retention_days * 86400,
                Inbox.status.in_(["pending", "failed"]),
            )
            .values(payload={}, status="expired", error="retention_expired")
        )
        session.execute(
            update(Outbox)
            .where(
                Outbox.created_at < now - settings.event_retention_days * 86400,
                Outbox.destination == "messenger",
                Outbox.status != "processing",
            )
            .values(payload={}, status="suppressed", error="retention_expired")
        )
        session.execute(
            update(Outbox)
            .where(
                Outbox.created_at < now - settings.event_retention_days * 86400,
                Outbox.status.in_(["delivered", "dry_run", "suppressed"]),
            )
            .values(payload={})
        )


def sync_seller(db, settings, integrations, now=None):
    if settings.delivery_mode != "live":
        return
    now = now or time.time()
    # A lease limits catalog polling to one worker. No database transaction spans HTTP.
    with db.sessions.begin() as session:
        insert_once(session, Record, {"key": "seller-sync", "value": {}, "updated_at": 0}, "key")
        marker = session.scalar(
            select(Record).where(Record.key == "seller-sync").with_for_update(skip_locked=True)
        )
        if not marker or now - marker.updated_at < 60:
            return
        marker.updated_at = now
    health = {}
    try:
        document = integrations.read_catalog()
        with db.sessions.begin() as session:
            import_catalog(session, document, now)
        health["catalog"] = {"ok": True, "last_success": now}
    except Exception as exc:
        log.error("seller_catalog_failed", extra={"error_code": type(exc).__name__})
        health["catalog"] = {"ok": False, "error": type(exc).__name__}
    try:
        for row_number, row in integrations.commands():
            command_id, order_id, version, action, _ = row
            try:
                import re

                if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", command_id):
                    raise OrderConflict("invalid_command_id")
                with db.sessions.begin() as session:
                    if action in {"pause", "resume"}:
                        order = session.get(Order, order_id)
                        if not order:
                            raise OrderConflict("not_found")
                        conversation = session.scalar(
                            select(Conversation)
                            .where(Conversation.key == order.conversation_key)
                            .with_for_update()
                        )
                        key = f"seller-control:{command_id}"
                        prior = session.get(Record, key)
                        if prior and prior.value != {"action": action, "order_id": order_id}:
                            raise OrderConflict("command_reused")
                        if not prior:
                            conversation.paused = action == "pause"
                            session.add(
                                Record(key=key, value={"action": action, "order_id": order_id})
                            )
                    else:
                        change_status(
                            session,
                            order_id,
                            int(version),
                            action,
                            command_id,
                            now,
                            actor="seller_sheet",
                        )
                result = "accepted"
            except (OrderConflict, ValueError) as exc:
                result = "rejected:" + (
                    str(exc) if isinstance(exc, OrderConflict) else "invalid_version"
                )
            integrations.command_result(row_number, row, result)
        health["commands"] = {"ok": True, "last_success": now}
    except Exception as exc:
        log.error("seller_commands_failed", extra={"error_code": type(exc).__name__})
        health["commands"] = {"ok": False, "error": type(exc).__name__}
    with db.sessions.begin() as session:
        marker = session.get(Record, "seller-sync")
        value = dict(marker.value)
        for key, outcome in health.items():
            previous = value.get(key, {})
            value[key] = {**previous, **outcome}
            if outcome["ok"]:
                value[key].pop("error", None)
        value["ok"] = all(outcome["ok"] for outcome in health.values())
        if value["ok"]:
            value["last_success"] = now
            value.pop("error", None)
        else:
            value["error"] = next(v["error"] for v in health.values() if not v["ok"])
        marker.value = value


def run():
    from tindabot.logging_setup import configure_logging

    configure_logging()
    settings = Settings()
    db, integrations = Database(settings), Integrations(settings)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            try:
                with db.sessions.begin() as session:
                    insert_once(session, Record, {"key": "worker-heartbeat", "value": {}}, "key")
                    session.get(Record, "worker-heartbeat").updated_at = time.time()
                busy = process_one(db, settings)
                busy = dispatch_one(db, settings, integrations) or busy
                maintenance(db, settings)
                sync_seller(db, settings, integrations)
                if not busy:
                    time.sleep(settings.worker_poll_seconds)
            except Exception as exc:
                log.error("worker_iteration_failed", extra={"error_code": type(exc).__name__})
                time.sleep(settings.worker_poll_seconds)
    finally:
        integrations.close()
        db.engine.dispose()


if __name__ == "__main__":
    run()
