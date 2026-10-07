import re
import time

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from tindabot.db import Product, Record, insert_once
from tindabot.orders import OrderConflict


class CatalogProduct(BaseModel):
    sku: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=80)
    price_minor: int = Field(ge=0, le=100_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    active: bool = True
    image_url: str = ""

    @field_validator("image_url")
    @classmethod
    def image_is_https(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Product images require HTTPS")
        return value


class FAQ(BaseModel):
    keywords: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=1800)


class CatalogImport(BaseModel):
    products: list[CatalogProduct] = Field(max_length=1000)
    faq: list[FAQ] = Field(default_factory=list, max_length=100)


def import_catalog(session, document: CatalogImport, now=None):
    now = now or time.time()
    skus = [p.sku for p in document.products]
    if len(skus) != len(set(skus)):
        raise ValueError("duplicate_sku")
    # All imports and adjustments serialize on one catalog row, then product keys.
    insert_once(session, Record, {"key": "catalog", "value": {}}, "key")
    record = session.scalar(select(Record).where(Record.key == "catalog").with_for_update())
    for item in sorted(document.products, key=lambda p: p.sku):
        existing = session.scalar(select(Product).where(Product.sku == item.sku).with_for_update())
        if existing:
            # Catalog refresh NEVER replenishes stock from stale Sheet data.
            for attr in ("name", "price_minor", "active", "image_url"):
                setattr(existing, attr, getattr(item, attr))
        else:
            session.add(Product(**item.model_dump()))
    for product in session.scalars(
        select(Product).where(Product.sku.not_in(skus)).order_by(Product.sku).with_for_update()
    ):
        product.active = False
    record.value = {
        "faq": [f.model_dump() for f in document.faq],
        "version": record.value.get("version", 0) + 1,
    }
    record.updated_at = now


def adjust_stock(session, sku, delta, command_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", command_id):
        raise OrderConflict("invalid_command_id")
    key = f"stock:{command_id}"
    insert_once(session, Record, {"key": "stock-lock", "value": {}}, "key")
    session.scalar(select(Record).where(Record.key == "stock-lock").with_for_update())
    prior = session.get(Record, key)
    if prior:
        if prior.value["sku"] != sku or prior.value["delta"] != delta:
            raise OrderConflict("command_reused")
        return prior.value
    product = session.scalar(select(Product).where(Product.sku == sku).with_for_update())
    if not product or product.stock + delta < 0:
        raise OrderConflict("invalid_adjustment")
    product.stock += delta
    result = {"sku": sku, "delta": delta, "stock": product.stock}
    session.add(Record(key=key, value=result))
    return result
