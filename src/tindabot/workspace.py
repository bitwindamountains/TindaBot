"""Authenticated, bounded read models and a public, data-free workspace shell."""

import base64
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Integer, and_, cast, func, or_, select

from tindabot.db import Inbox, Order, Outbox, Product, Record

WEB = Path(__file__).with_name("web")
DAY = 86_400
MANILA_OFFSET = 28_800


def register_workspace(app, db, settings, operator):
    app.mount(
        "/assets",
        GZipMiddleware(StaticFiles(directory=WEB), minimum_size=1000),
        name="workspace-assets",
    )

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
        payment: Literal["all", "unpaid", "paid", "refund_required"] = "all",
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
                "delivery_mode": settings.delivery_mode,
                "worker_age_seconds": max(0, now - heartbeat.updated_at) if heartbeat else None,
                "failures": failed + jobs.get("failed", 0) + jobs.get("uncertain", 0),
                "job_health": {
                    "inbox_failed": failed,
                    "delivery_failed": jobs.get("failed", 0),
                    "delivery_uncertain": jobs.get("uncertain", 0),
                },
                "queue": sum(jobs.get(status, 0) for status in ("pending", "processing")),
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
            }
