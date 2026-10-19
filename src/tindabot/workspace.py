"""Authenticated, bounded read models and a public, data-free workspace shell."""

import base64
import hashlib
import json
import math
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import Depends, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Integer, and_, cast, func, or_, select

from tindabot.db import Conversation, Inbox, Order, OrderActivity, Outbox, Product, Record
from tindabot.handover import waiting
from tindabot.machine import transition
from tindabot.messages import ORDER_UPDATES, order_update
from tindabot.orders import quote, refund_total
from tindabot.recovery import inspect_job
from tindabot.service import apply_actions, view_for

WEB = Path(__file__).with_name("web")
DAY = 86_400
MANILA_OFFSET = 28_800


def activity_page(session, order_id, before=None):
    query = select(OrderActivity).where(OrderActivity.order_id == order_id)
    if before is not None:
        query = query.where(OrderActivity.id < before)
    events = session.scalars(query.order_by(OrderActivity.id.desc()).limit(51)).all()
    return {
        "activity": [
            {
                "id": e.id,
                "kind": e.kind,
                "actor": e.actor,
                "version": e.order_version,
                "created_at": e.created_at,
                "occurred_at": e.occurred_at,
                "body": e.body,
                "amount_minor": e.amount_minor,
                "data": e.data,
            }
            for e in events[:50]
        ],
        "next_activity_cursor": events[49].id if len(events) > 50 else None,
    }


class TestChatMessage(BaseModel):
    state: Literal[
        "IDLE",
        "BROWSING",
        "QTY",
        "CART",
        "DELIVERY",
        "NAME",
        "PHONE",
        "ADDRESS",
        "PAYMENT",
        "CONFIRMING",
    ] = "IDLE"
    context: dict = Field(default_factory=dict)
    value: str = Field(min_length=1, max_length=2000)


def automation_insights(session, now):
    """How the bot did today, and this week's questions it could not answer."""
    today = int((now + MANILA_OFFSET) // DAY) * DAY - MANILA_OFFSET
    customer = Inbox.payload["echo"].as_boolean().is_(False)
    missed = Inbox.payload["missed"].as_boolean().is_(True)

    def conversations(*where):
        return set(session.scalars(select(Inbox.conversation_key).where(*where).distinct()))

    talked = conversations(customer, Inbox.occurred_at >= today)
    stuck = conversations(customer, missed, Inbox.occurred_at >= today)
    handed = set(
        session.scalars(
            select(Outbox.conversation_key)
            .where(Outbox.business_key.startswith("handover:"), Outbox.created_at >= today)
            .distinct()
        )
    )
    needed = (stuck | handed) & talked
    groups = {}
    # ponytail: exact normalized grouping; add keyword overlap if pilot data shows Taglish variants rarely repeat.
    for payload, occurred in session.execute(
        select(Inbox.payload, Inbox.occurred_at)
        .where(customer, missed, Inbox.occurred_at >= today - 6 * DAY)
        .order_by(Inbox.occurred_at.desc())
        .limit(500)
    ):
        value = payload.get("value", "")
        key = " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())
        if not key or payload.get("postback"):
            continue
        group = groups.setdefault(key, {"text": value[:200], "keywords": key, "count": 0})
        group["count"] += 1
        group.setdefault("last_at", occurred)
    misses = sorted(groups.values(), key=lambda g: (-g["count"], -g["last_at"]))
    return {
        "conversations": len(talked),
        "self_served": len(talked - needed),
        "needed_you": len(needed),
        "missed_week": sum(g["count"] for g in misses),
        "misses": misses[:10],
    }


def register_workspace(app, db, settings, operator):
    @app.get("/admin/workspace/handovers", dependencies=[Depends(operator)])
    def handovers(response: Response, after: str | None = Query(default=None, max_length=150)):
        response.headers["Cache-Control"] = "no-store"
        query = select(Conversation).where(
            *waiting(), Conversation.key.startswith(settings.meta_page_id + ":", autoescape=True)
        )
        if after:
            query = query.where(Conversation.key > after)
        with db.sessions() as session:
            rows = session.scalars(query.order_by(Conversation.key).limit(51)).all()
            names = {
                c.key: session.scalar(
                    select(Order.details["name"].as_string())
                    .where(Order.conversation_key == c.key, Order.anonymized.is_(False))
                    .order_by(Order.created_at.desc(), Order.id.desc())
                    .limit(1)
                )
                for c in rows[:50]
            }
            return {
                "conversations": [
                    {
                        "psid": c.psid,
                        "name": c.context.get("name") or names[c.key] or "Customer",
                        "version": c.version,
                        "last_customer_at": c.last_customer_at,
                        "reason": c.context["handover"]["reason"],
                        "since": c.context["handover"]["since"],
                    }
                    for c in rows[:50]
                ],
                "next_cursor": rows[49].key if len(rows) > 50 else None,
                "inbox_url": "https://business.facebook.com/latest/inbox/all/",
            }

    @app.get("/admin/workspace/jobs", dependencies=[Depends(operator)])
    def delivery_jobs(
        response: Response,
        status: Literal["all", "failed", "uncertain"] = "all",
        before: int | None = Query(default=None, ge=1),
    ):
        response.headers["Cache-Control"] = "no-store"
        query = select(Outbox).where(Outbox.status.in_(["failed", "uncertain"]))
        if status != "all":
            query = query.where(Outbox.status == status)
        if before is not None:
            query = query.where(Outbox.id < before)
        with db.sessions() as session:
            jobs = session.scalars(query.order_by(Outbox.id.desc()).limit(51)).all()
            return {
                "jobs": [inspect_job(job) for job in jobs[:50]],
                "next_cursor": jobs[49].id if len(jobs) > 50 else None,
            }

    app.mount(
        "/assets",
        GZipMiddleware(StaticFiles(directory=WEB), minimum_size=1000),
        name="workspace-assets",
    )

    @app.post("/admin/workspace/test-chat", dependencies=[Depends(operator)])
    def test_chat(message: TestChatMessage):
        """Run the live conversation logic against the real catalog. Nothing is saved or sent."""
        stale = HTTPException(422, "Test conversation is out of date; start over")
        context = message.context
        try:
            size = len(json.dumps(context, allow_nan=False))
        except (ValueError, RecursionError) as exc:
            raise stale from exc
        if size > 8000:
            raise HTTPException(422, "Test conversation is too long; start over")
        cart = context.get("cart", {})
        if (
            not isinstance(cart, dict)
            or len(cart) > 20
            or not all(
                isinstance(sku, str) and type(qty) is int and 1 <= qty <= 99
                for sku, qty in cart.items()
            )
        ):
            raise stale
        now = time.time()
        with db.sessions() as session:
            # The test conversation owns no orders, so tracking replies stay empty.
            view = view_for(session, SimpleNamespace(key="workspace-test-chat"), settings, now)
            try:
                if "quote" in context:
                    # Derived data is recomputed here; a browser-sent quote is never trusted.
                    context = {**context, "quote": quote(session, context, settings)}
                decision = transition(message.state, context, message.value, view)
                replies, _ = apply_actions(
                    session,
                    decision,
                    settings,
                    view,
                    place_order=lambda ctx: (SimpleNamespace(code="TEST-ORDER"), False),
                    hand_over=lambda ctx: None,
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
                RecursionError,
                OverflowError,
            ) as exc:
                raise stale from exc
            finally:
                session.rollback()
        return {
            "state": decision.state,
            "context": decision.context,
            "replies": replies,
            "handed_over": "pause" in decision.actions,
            "catalog_fresh": view["catalog_fresh"],
        }

    @app.get("/", include_in_schema=False)
    def workspace():
        return FileResponse(
            WEB / "index.html",
            headers={
                "Cache-Control": "no-cache",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/admin/workspace", dependencies=[Depends(operator)])
    def snapshot(
        response: Response,
        days: int = Query(default=7, ge=1, le=30),
        scope: Literal["period", "all", "open"] = "period",
        status: Literal["all", "pending", "confirmed", "shipped", "delivered", "cancelled"] = "all",
        payment: Literal["all", "unpaid", "paid", "refund_required", "refunded"] = "all",
        sort: Literal["newest", "oldest", "highest", "lowest"] = "newest",
        q: str = Query(default="", max_length=200),
        cursor: str | None = Query(default=None, max_length=2048),
    ):
        response.headers["Cache-Control"] = "no-store"
        now = time.time()
        today = int((now + MANILA_OFFSET) // DAY)
        start = (today - days + 1) * DAY - MANILA_OFFSET
        period = (Order.created_at >= start, Order.created_at <= now)
        signature = hashlib.sha256(
            json.dumps([days, scope, status, payment, sort, q]).encode()
        ).hexdigest()
        anchor, after = now, None
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor))
                anchor, value, order_id, fingerprint = decoded
                if (
                    fingerprint != signature
                    or not isinstance(anchor, (int, float))
                    or not math.isfinite(anchor)
                    or not 0 <= anchor <= now
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not isinstance(order_id, str)
                    or not 1 <= len(order_id) <= 36
                ):
                    raise ValueError("invalid_cursor")
                after = (value, order_id)
            except (ValueError, TypeError, OverflowError) as exc:
                raise HTTPException(422, "Invalid order cursor") from exc
        order_scope = [Order.created_at <= anchor]
        if scope == "period":
            anchor_day = int((anchor + MANILA_OFFSET) // DAY)
            order_scope.append(Order.created_at >= (anchor_day - days + 1) * DAY - MANILA_OFFSET)
        elif scope == "open":
            order_scope.append(
                or_(
                    Order.status.in_(["pending", "confirmed", "shipped"]),
                    Order.payment_status == "refund_required",
                    and_(Order.payment_status == "unpaid", Order.status != "cancelled"),
                )
            )
        if payment != "all":
            order_scope.append(Order.payment_status == payment)
        if q.strip():
            search = q.strip().lower()
            order_scope.append(
                or_(
                    func.lower(Order.code).contains(search, autoescape=True),
                    func.lower(Order.details["name"].as_string()).contains(search, autoescape=True),
                )
            )
        filters = [*order_scope]
        if status != "all":
            filters.append(Order.status == status)
        column = Order.total_minor if sort in {"highest", "lowest"} else Order.created_at
        descending = sort in {"newest", "highest"}
        page_filters = [*filters]
        if after:
            value, order_id = after
            page_filters.append(
                or_(
                    column < value if descending else column > value,
                    and_(column == value, Order.id > order_id),
                )
            )
        with db.sessions() as session:
            count = session.scalar(select(func.count()).select_from(Order).where(*period))
            value = session.scalar(
                select(func.coalesce(func.sum(Order.total_minor), 0)).where(
                    *period, Order.status != "cancelled"
                )
            )
            pending = session.scalar(
                select(func.count()).select_from(Order).where(Order.status == "pending")
            )
            active = session.scalar(
                select(func.count()).select_from(Product).where(Product.active.is_(True))
            )
            bucket = cast(func.floor((Order.created_at + MANILA_OFFSET) / DAY), Integer)
            daily = dict(
                session.execute(
                    select(bucket, func.sum(Order.total_minor))
                    .where(*period, Order.status != "cancelled")
                    .group_by(bucket)
                ).all()
            )
            orders = session.scalars(
                select(Order)
                .where(*page_filters)
                .order_by(column.desc() if descending else column.asc(), Order.id)
                .limit(201)
            ).all()
            has_more = len(orders) > 200
            orders = orders[:200]
            next_cursor = None
            if has_more:
                last = orders[-1]
                cursor_value = (
                    last.total_minor if sort in {"highest", "lowest"} else last.created_at
                )
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps([anchor, cursor_value, last.id, signature]).encode()
                ).decode()
            order_count = session.scalar(select(func.count()).select_from(Order).where(*filters))
            order_counts = dict(
                session.execute(
                    select(Order.status, func.count()).where(*order_scope).group_by(Order.status)
                ).all()
            )
            products = session.scalars(
                select(Product).order_by(Product.name, Product.sku).limit(500)
            ).all()
            product_count = session.scalar(select(func.count()).select_from(Product))
            heartbeat = session.get(Record, "worker-heartbeat")
            control = session.get(Record, "automation")
            updates = session.get(Record, "order-updates")
            failed = session.scalar(
                select(func.count()).select_from(Inbox).where(Inbox.status == "failed")
            )
            jobs = dict(
                session.execute(select(Outbox.status, func.count()).group_by(Outbox.status)).all()
            )
            return {
                "shop_name": settings.shop_name,
                "generated_at": now,
                "days": days,
                "summary": {
                    "order_value": value,
                    "orders": count,
                    "pending": pending,
                    "products": active,
                },
                "series": [
                    {"timestamp": day * DAY - MANILA_OFFSET, "value": daily.get(day, 0)}
                    for day in range(today - days + 1, today + 1)
                ],
                "orders": [
                    {
                        "id": order.id,
                        "code": order.code,
                        "name": order.details.get("name", "Customer"),
                        "total_minor": order.total_minor,
                        "status": order.status,
                        "payment_status": order.payment_status,
                        "version": order.version,
                        "created_at": order.created_at,
                        "item_count": sum(item.get("qty", 0) for item in order.items),
                    }
                    for order in orders
                ],
                "orders_truncated": has_more,
                "order_total": order_count,
                "order_counts": order_counts,
                "next_cursor": next_cursor,
                "products": [
                    {
                        "sku": p.sku,
                        "name": p.name,
                        "price_minor": p.price_minor,
                        "stock": p.stock,
                        "active": p.active,
                    }
                    for p in products
                ],
                "products_truncated": product_count > len(products),
                "automation": settings.automation_enabled
                and (control.value.get("enabled", True) if control else True),
                "automation_locked": not settings.automation_enabled,
                "order_updates": {
                    event: bool(updates and updates.value.get(event)) for event in ORDER_UPDATES
                },
                "order_update_tag": settings.order_update_tag,
                "order_update_examples": {
                    event: order_update("TB-1048", event, pickup=False) for event in ORDER_UPDATES
                },
                "delivery_mode": settings.delivery_mode,
                "worker_age_seconds": max(0, now - heartbeat.updated_at) if heartbeat else None,
                "failures": failed + jobs.get("failed", 0) + jobs.get("uncertain", 0),
                "job_health": {
                    "inbox_failed": failed,
                    "delivery_failed": jobs.get("failed", 0),
                    "delivery_uncertain": jobs.get("uncertain", 0),
                },
                "queue": sum(jobs.get(status, 0) for status in ("pending", "processing")),
                "insights": automation_insights(session, now),
                "sheet_url": f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/edit"
                if settings.google_sheet_id
                else None,
                "handover_count": session.scalar(
                    select(func.count())
                    .select_from(Conversation)
                    .where(
                        *waiting(),
                        Conversation.key.startswith(settings.meta_page_id + ":", autoescape=True),
                    )
                ),
            }

    @app.get("/admin/workspace/orders/{order_id}", dependencies=[Depends(operator)])
    def order_detail(order_id: str, response: Response):
        response.headers["Cache-Control"] = "no-store"
        with db.sessions() as session:
            order = session.get(Order, order_id)
            if not order:
                raise HTTPException(404, "Order not found")
            return {
                "id": order.id,
                "code": order.code,
                "details": order.details,
                "items": order.items,
                "total_minor": order.total_minor,
                "shipping_minor": order.shipping_minor,
                "status": order.status,
                "payment_status": order.payment_status,
                "version": order.version,
                "created_at": order.created_at,
                "anonymized": order.anonymized,
                "refunded_minor": refund_total(session, order.id),
                **activity_page(session, order.id),
            }

    @app.get("/admin/workspace/orders/{order_id}/activity", dependencies=[Depends(operator)])
    def order_activity(
        order_id: str, response: Response, before: int | None = Query(default=None, ge=1)
    ):
        response.headers["Cache-Control"] = "no-store"
        with db.sessions() as session:
            if not session.get(Order, order_id):
                raise HTTPException(404, "Order not found")
            return activity_page(session, order_id, before)
