import hashlib
import json
import secrets
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from tindabot.db import Order, OrderActivity, Product, Record, enqueue, insert_once


class OrderConflict(ValueError):
    pass


def quote(session, context, settings, *, lock=False):
    if not context.get("cart"):
        raise OrderConflict("empty_cart")
    items = []
    for sku, qty in sorted(context["cart"].items()):
        query = select(Product).where(Product.sku == sku)
        p = session.scalar(
            query.with_for_update().execution_options(populate_existing=True) if lock else query
        )
        if not p or not p.active or not isinstance(qty, int) or not 1 <= qty <= 99 or p.stock < qty:
            raise OrderConflict("unavailable")
        items.append({"sku": sku, "name": p.name, "price_minor": p.price_minor, "qty": qty})
    if context["payment"] not in settings.payments:
        raise OrderConflict("payment_unavailable")
    shipping = settings.shipping_minor if context["delivery"] == "delivery" else 0
    total = shipping + sum(i["qty"] * i["price_minor"] for i in items)
    if total > 2_000_000_000:
        raise OrderConflict("total_too_large")
    instructions = {
        "cod": "Pay the seller on delivery.",
        "gcash": settings.gcash_instructions,
        "bank": settings.bank_instructions,
    }[context["payment"]]
    return {
        "items": items,
        "shipping_minor": shipping,
        "total_minor": total,
        "instructions": instructions,
        "pickup_address": settings.pickup_address,
    }


def create_order(session, conversation, ctx, settings, now):
    existing = session.scalar(select(Order).where(Order.checkout_id == ctx["checkout_id"]))
    if existing:
        return existing, False
    current = quote(session, ctx, settings, lock=True)
    if current != ctx.get("quote"):
        ctx["quote"] = current
        ctx["version"] += 1
        return None, True
    for item in current["items"]:
        session.get(Product, item["sku"]).stock -= item["qty"]
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    # A rare uniqueness collision rolls the entire event transaction back; the
    # bounded event retry generates a fresh code without double-allocating stock.
    code = (
        "TB-"
        + datetime.fromtimestamp(now, UTC).strftime("%y%m%d")
        + "-"
        + "".join(secrets.choice(alphabet) for _ in range(10))
    )
    order = Order(
        id=str(uuid.uuid4()),
        code=code,
        checkout_id=ctx["checkout_id"],
        conversation_key=conversation.key,
        details={k: ctx.get(k, "") for k in ("name", "phone", "address", "delivery", "payment")},
        items=current["items"],
        total_minor=current["total_minor"],
        shipping_minor=current["shipping_minor"],
        expires_at=now + settings.unpaid_expiry_hours * 3600 if ctx["payment"] != "cod" else None,
        created_at=now,
    )
    session.add(order)
    session.flush()
    record_activity(session, order, "created", "customer", now)
    enqueue(session, key=f"sheet:{order.id}:1", destination="sheets", order=order.id)
    enqueue(session, key=f"email:{order.id}", destination="email", order=order.id)
    return order, False


ALLOWED = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def record_activity(session, order, kind, actor, now, **fields):
    event = OrderActivity(
        order_id=order.id,
        kind=kind,
        actor=actor,
        order_version=order.version,
        created_at=now,
        occurred_at=fields.pop("occurred_at", now),
        **fields,
    )
    session.add(event)
    return event


def refund_total(session, order_id):
    return session.scalar(
        select(func.coalesce(func.sum(OrderActivity.amount_minor), 0)).where(
            OrderActivity.order_id == order_id, OrderActivity.kind == "refund"
        )
    )


def apply_order_action(
    session,
    order_id,
    expected_version,
    command_id,
    kind,
    body,
    *,
    amount_minor=None,
    occurred_at=None,
    now=None,
):
    """Append a private note or reconcile an external refund, never send money."""
    now = time.time() if now is None else now
    body = body.strip()
    fingerprint = hashlib.sha256(
        json.dumps([kind, order_id, body, amount_minor, occurred_at], ensure_ascii=False).encode()
    ).hexdigest()
    key = f"command:{command_id}"
    if not insert_once(session, Record, {"key": key, "value": {}, "updated_at": now}, "key"):
        prior = session.get(Record, key).value
        if prior.get("fingerprint") != fingerprint:
            raise OrderConflict("command_reused")
        return prior["result"]
    order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise OrderConflict("not_found")
    if order.version != expected_version:
        raise OrderConflict("version_conflict")
    fields = {}
    if kind == "note":
        if order.anonymized:
            raise OrderConflict("notes_erased")
        if not body or len(body) > 2000:
            raise OrderConflict("invalid_note")
        fields["body"] = body
    elif kind == "refund":
        if order.status != "cancelled" or order.payment_status != "refund_required":
            raise OrderConflict("refund_unavailable")
        refunded = refund_total(session, order.id)
        if (
            not isinstance(amount_minor, int)
            or amount_minor <= 0
            or amount_minor > order.total_minor - refunded
        ):
            raise OrderConflict("refund_exceeds_remaining")
        if len(body) > 160 or (not order.anonymized and not body):
            raise OrderConflict("refund_reference_required")
        completed = now if occurred_at is None else occurred_at
        if not order.created_at <= completed <= now:
            raise OrderConflict("refund_date_invalid")
        fields.update(
            amount_minor=amount_minor,
            occurred_at=completed,
            body=None if order.anonymized else body,
        )
        if refunded + amount_minor == order.total_minor:
            order.payment_status = "refunded"
    else:
        raise OrderConflict("invalid_action")
    order.version += 1
    event = record_activity(session, order, kind, "operator", now, **fields)
    session.flush()
    result = {
        "order_id": order.id,
        "activity_id": event.id,
        "version": order.version,
        "payment_status": order.payment_status,
        "refunded_minor": refund_total(session, order.id),
    }
    session.get(Record, key).value = {"fingerprint": fingerprint, "result": result}
    # Keep Sheet command versions current, without exporting private notes or references.
    enqueue(session, key=f"sheet:{order.id}:{order.version}", destination="sheets", order=order.id)
    return result


def change_status(
    session, order_id, expected_version, status, command_id, now=None, *, actor="operator"
):
    now = now or time.time()
    key = f"command:{command_id}"
    # Reserve a globally unique command record before changing any order. Concurrent
    # reuse, even against different orders, waits for the first transaction to finish.
    inserted = insert_once(session, Record, {"key": key, "value": {}, "updated_at": now}, "key")
    if not inserted:
        prior = session.get(Record, key)
        if prior.value.get("order_id") != order_id or prior.value.get("status") != status:
            raise OrderConflict("command_reused")
        return prior.value
    order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise OrderConflict("not_found")
    if order.version != expected_version:
        raise OrderConflict("version_conflict")
    previous = {"status": order.status, "payment_status": order.payment_status}
    if status == "paid":
        if order.status == "cancelled" or order.payment_status == "paid":
            raise OrderConflict("invalid_transition")
        order.payment_status = "paid"
        order.expires_at = None
    elif status in ALLOWED.get(order.status, set()):
        if (
            status in {"shipped", "delivered"}
            and order.details.get("payment") != "cod"
            and order.payment_status != "paid"
        ):
            raise OrderConflict("payment_unverified")
        order.status = status
        if status == "cancelled" and not order.stock_released:
            for item in sorted(order.items, key=lambda item: item["sku"]):
                product = session.scalar(
                    select(Product).where(Product.sku == item["sku"]).with_for_update()
                )
                product.stock += item["qty"]
            order.stock_released = True
            if order.payment_status == "paid":
                order.payment_status = "refund_required"
    else:
        raise OrderConflict("invalid_transition")
    order.version += 1
    record_activity(
        session,
        order,
        "status",
        actor,
        now,
        data={
            "before": previous,
            "after": {"status": order.status, "payment_status": order.payment_status},
        },
    )
    result = {"order_id": order.id, "status": status, "version": order.version}
    session.get(Record, key).value = result
    enqueue(session, key=f"sheet:{order.id}:{order.version}", destination="sheets", order=order.id)
    return result
