import hashlib
import time

from sqlalchemy import select

from tindabot.db import Conversation, Inbox, Order, Outbox, Record, enqueue


def erase_customer(session, conversation_key, now=None):
    """Erase controlled PII and enqueue Sheet erasure. Retain minimal ledger metadata.

    Already delivered email and Meta data require the seller/provider workflow.
    Caller must verify identity and retention obligations before invoking this operation.
    """
    now = now or time.time()
    conversation = session.scalar(
        select(Conversation).where(Conversation.key == conversation_key).with_for_update()
    )
    if not conversation:
        return {"orders": 0}
    # Operator must resolve in-flight sends; deleting a payload while it is being
    # sent cannot recall the copy already read by another worker.
    active = session.scalar(
        select(Outbox.id)
        .where(Outbox.conversation_key == conversation_key, Outbox.status == "processing")
        .limit(1)
    )
    if active:
        raise ValueError("delivery_in_progress")
    conversation.context, conversation.state, conversation.paused = {}, "IDLE", True
    for event in session.scalars(select(Inbox).where(Inbox.conversation_key == conversation_key)):
        event.payload, event.status = {}, "expired"
    for job in session.scalars(select(Outbox).where(Outbox.conversation_key == conversation_key)):
        job.payload, job.status = {}, "suppressed"
    orders = session.scalars(
        select(Order)
        .where(Order.conversation_key == conversation_key)
        .order_by(Order.id)
        .with_for_update()
    ).all()
    for order in orders:
        order.details = {k: v for k, v in order.details.items() if k in {"delivery", "payment"}}
        order.anonymized = True
        order.version += 1
        enqueue(
            session, key=f"erasure:{order.id}:{order.version}", destination="sheets", order=order.id
        )
    identity_hash = hashlib.sha256(conversation_key.encode()).hexdigest()
    session.add(
        Record(
            key=f"erasure:{identity_hash}:{int(now)}",
            value={"identity_hash": identity_hash, "order_ids": [o.id for o in orders]},
            updated_at=now,
        )
    )
    # Page-scoped identity remains restricted operational metadata for suppression
    # and accounting ownership; this is personal-field erasure, not full unlinking.
    return {"orders": len(orders), "sheet_erasure": "queued"}
