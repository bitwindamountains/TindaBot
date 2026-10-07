import secrets
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from tindabot.db import Order, Product, Record, enqueue, insert_once


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


def change_status(session, order_id, expected_version, status, command_id, now=None):
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
    result = {"order_id": order.id, "status": status, "version": order.version}
    session.get(Record, key).value = result
    enqueue(session, key=f"sheet:{order.id}:{order.version}", destination="sheets", order=order.id)
    return result
