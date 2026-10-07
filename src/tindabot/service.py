import time
import uuid

from sqlalchemy import func, select

from tindabot.db import Conversation, Inbox, Order, Product, Record, enqueue
from tindabot.machine import transition
from tindabot.messages import COPY, MENU, confirmation, money, summary, text
from tindabot.orders import OrderConflict, create_order, quote


def view_for(session, conversation, settings, now):
    catalog = session.get(Record, "catalog")
    products = [
        {
            "sku": p.sku,
            "name": p.name,
            "price_minor": p.price_minor,
            "stock": p.stock,
            "image_url": p.image_url,
        }
        for p in session.scalars(
            select(Product).where(Product.active.is_(True)).order_by(Product.sku)
        )
    ]
    orders = session.scalars(
        select(Order)
        .where(Order.conversation_key == conversation.key)
        .order_by(Order.created_at.desc())
        .limit(3)
    ).all()
    tracking = (
        "\n".join(
            f"{o.code}: {o.status} / {o.payment_status} — {money(o.total_minor)}" for o in orders
        )
        or COPY["none"]
    )
    return {
        "products": products,
        "catalog_fresh": bool(
            catalog and now - catalog.updated_at <= settings.catalog_max_age_seconds
        ),
        "faq": catalog.value.get("faq", []) if catalog else [],
        "tracking": tracking,
        "shop_name": settings.shop_name,
        "privacy_url": settings.privacy_url,
        "new_id": str(uuid.uuid4()),
        "now": now,
        "payments": settings.payments,
    }


def process_one(db, settings, now=None, before_commit=None):
    now = now or time.time()
    event_id = None
    try:
        with db.sessions.begin() as session:
            earliest = (
                select(Inbox.conversation_key, func.min(Inbox.id).label("first_id"))
                .where(Inbox.status.in_(["pending", "failed"]))
                .group_by(Inbox.conversation_key)
                .subquery()
            )
            candidate = (
                select(Conversation)
                .join(earliest, Conversation.key == earliest.c.conversation_key)
                .join(Inbox, Inbox.id == earliest.c.first_id)
                .where(Inbox.status == "pending", Inbox.next_attempt <= now)
                .order_by(Inbox.id)
                .with_for_update(skip_locked=True, of=Conversation)
                .limit(1)
            )
            conversation = session.scalar(candidate)
            if not conversation:
                return False
            event = session.scalar(
                select(Inbox)
                .where(
                    Inbox.conversation_key == conversation.key,
                    Inbox.status.in_(["pending", "failed"]),
                )
                .order_by(Inbox.id)
                .limit(1)
            )
            if event.status != "pending" or event.next_attempt > now:
                return False
            event_id = event.id
            payload = event.payload
            replies = []
            receipt = False
            if payload.get("echo"):
                # Conservative handover: unknown external Page send pauses automation.
                # Known own sends are correlated by returned message ID as well as app ID.
                own = payload.get("app_id") == settings.meta_app_id and bool(settings.meta_app_id)
                known = (
                    session.get(Record, f"sent:{payload.get('mid')}")
                    if payload.get("mid")
                    else None
                )
                if not own and not known:
                    conversation.paused = True
            else:
                # Delayed deliveries never reopen the window using receipt time.
                conversation.last_customer_at = max(
                    conversation.last_customer_at, event.occurred_at
                )
                command = payload.get("value", "").strip().upper()
                if command in {"MENU", "GET_STARTED"} and now - event.occurred_at < 86400:
                    conversation.paused = False
                minute = int(now // 60)
                conversation.rate_count = (
                    conversation.rate_count + 1 if conversation.rate_minute == minute else 1
                )
                conversation.rate_minute = minute
                control = session.get(Record, "automation")
                enabled = settings.automation_enabled and (
                    not control or control.value.get("enabled", True)
                )
                if (
                    not conversation.paused
                    and enabled
                    and (
                        conversation.rate_count <= settings.max_messages_per_minute
                        or command
                        in {
                            "MENU",
                            "GET_STARTED",
                            "SELLER",
                            "STOP",
                            "AGENT",
                            "TAO",
                            "TALK_TO_SELLER",
                            "CANCEL",
                        }
                    )
                    and now - event.occurred_at < 86400
                ):
                    if (
                        now - conversation.updated_at > 86400
                        or now - conversation.context.get("draft_created_at", now) > 86400
                    ):
                        conversation.state, conversation.context = "IDLE", {}
                    view = view_for(session, conversation, settings, now)
                    decision = transition(
                        conversation.state, conversation.context, payload.get("value", ""), view
                    )
                    replies = decision.replies
                    ctx = decision.context
                    for action in decision.actions:
                        if action == "pause":
                            conversation.paused = True
                            enqueue(
                                session,
                                key=f"handover:{event.id}",
                                destination="email",
                                conversation=conversation.key,
                                payload={"handover": True},
                            )
                        elif action in {"quote", "confirm"}:
                            try:
                                if not view["catalog_fresh"]:
                                    raise OrderConflict("stale_catalog")
                                if action == "quote":
                                    ctx["quote"] = quote(session, ctx, settings)
                                else:
                                    order, changed = create_order(
                                        session, conversation, ctx, settings, now
                                    )
                                    if order:
                                        receipt = True
                                        replies = confirmation(
                                            order.code, ctx["payment"], ctx["quote"]["instructions"]
                                        )
                                        decision.state, decision.context = "IDLE", {}
                                        break
                                    if changed:
                                        replies += text(COPY["changed"])
                                replies += text(
                                    summary(ctx),
                                    [
                                        (
                                            "Confirm",
                                            f"CONFIRM:{ctx['checkout_id']}:{ctx['version']}",
                                        ),
                                        ("Edit", "EDIT"),
                                        ("Cancel", "CANCEL"),
                                    ],
                                )
                            except OrderConflict as exc:
                                replies = text(
                                    COPY["catalog_unavailable"]
                                    if str(exc) == "stale_catalog"
                                    else COPY["unavailable"],
                                    MENU,
                                )
                                decision.state = "CART"
                                ctx.pop("quote", None)
                                if str(exc) == "unavailable":
                                    available = {
                                        p.sku: p
                                        for p in session.scalars(
                                            select(Product)
                                            .where(Product.active.is_(True))
                                            .execution_options(populate_existing=True)
                                        )
                                    }
                                    ctx["cart"] = {
                                        sku: qty
                                        for sku, qty in ctx.get("cart", {}).items()
                                        if sku in available and available[sku].stock >= qty
                                    }
                    conversation.state, conversation.context = decision.state, decision.context
                conversation.updated_at = now
                conversation.version += 1
            for index, reply in enumerate(replies):
                enqueue(
                    session,
                    key=f"reply:{event.id}:{index}",
                    destination="messenger",
                    conversation=conversation.key,
                    payload={
                        "message": reply,
                        "allow_paused": bool(conversation.paused and replies),
                        "event_at": event.occurred_at,
                        "conversation_version": conversation.version,
                        "receipt": receipt,
                    },
                )
            event.status = "done"
            event.error = None
            if before_commit:
                before_commit()
        return True
    except Exception as exc:
        if event_id is None:
            raise
        with db.sessions.begin() as session:
            event = session.scalar(select(Inbox).where(Inbox.id == event_id).with_for_update())
            if event and event.status == "pending":
                event.attempts += 1
                event.error = type(exc).__name__[:100]
                event.next_attempt = now + min(300, 2**event.attempts)
                if event.attempts >= settings.max_attempts:
                    event.status = "failed"
        return True
