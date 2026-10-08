import hashlib
import time

from sqlalchemy import or_, select, update

from tindabot.db import Conversation, Inbox, Order, OrderActivity, Outbox, Record, enqueue
from tindabot.orders import record_activity


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
    orders = session.scalars(
        select(Order)
        .where(Order.conversation_key == conversation_key)
        .order_by(Order.id)
        .with_for_update()
    ).all()
    # Lock the same job rows claimed by the dispatcher. If a claim wins, inspect
    # its committed processing state; if erasure wins, SKIP LOCKED cannot claim it.
    # Order locks also serialize status changes that enqueue new exports.
    jobs = session.scalars(
        select(Outbox)
        .where(
            or_(
                Outbox.conversation_key == conversation_key,
                Outbox.order_id.in_([order.id for order in orders]),
            )
        )
        .order_by(Outbox.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if any(job.status == "processing" for job in jobs):
        raise ValueError("delivery_in_progress")
    conversation.context, conversation.state, conversation.paused = {}, "IDLE", True
    conversation.version += 1
    for event in session.scalars(select(Inbox).where(Inbox.conversation_key == conversation_key)):
        event.payload, event.status = {}, "expired"
    for job in jobs:
        job.payload = {}
        if job.status in {"pending", "failed", "uncertain"}:
            job.status, job.error = "suppressed", "customer_erasure"
    for order in orders:
        order.details = {k: v for k, v in order.details.items() if k in {"delivery", "payment"}}
        order.anonymized = True
        order.version += 1
        session.execute(
            update(OrderActivity).where(OrderActivity.order_id == order.id).values(body=None)
        )
        record_activity(session, order, "erased", "operator", now)
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
