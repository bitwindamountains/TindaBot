"""Authenticated, bounded read models and a public, data-free workspace shell."""

import time
from pathlib import Path

from fastapi import Depends, HTTPException, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Integer, cast, func, select

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
    def snapshot(response: Response, days: int = Query(default=7, ge=1, le=30)):
        response.headers["Cache-Control"] = "no-store"
        now = time.time()
        today = int((now + MANILA_OFFSET) // DAY)
        start = (today - days + 1) * DAY - MANILA_OFFSET
        period = (Order.created_at >= start, Order.created_at <= now)
        with db.sessions() as session:
            count = session.scalar(select(func.count()).select_from(Order).where(*period))
            value = session.scalar(
                select(func.coalesce(func.sum(Order.total_minor), 0)).where(
                    *period, Order.status != "cancelled"
                )
            )
            pending = session.scalar(
                select(func.count()).select_from(Order).where(*period, Order.status == "pending")
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
                select(Order).where(*period).order_by(Order.created_at.desc(), Order.id).limit(200)
            ).all()
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
                "orders_truncated": count > len(orders),
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
