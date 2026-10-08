import time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from tindabot.config import Settings


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    key: Mapped[str] = mapped_column(String(150), primary_key=True)
    psid: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(32), default="IDLE")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)
    last_customer_at: Mapped[float] = mapped_column(Float, default=0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_minute: Mapped[int] = mapped_column(Integer, default=0)
    rate_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Inbox(Base):
    __tablename__ = "inbound_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(200), unique=True)
    conversation_key: Mapped[str] = mapped_column(ForeignKey("conversations.key"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[float] = mapped_column(Float)
    received_at: Mapped[float] = mapped_column(Float, default=time.time)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (Index("ix_inbox_due", "status", "next_attempt", "id"),)


class Product(Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_minor: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("price_minor >= 0"), CheckConstraint("stock >= 0"))


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    checkout_id: Mapped[str] = mapped_column(String(36), unique=True)
    conversation_key: Mapped[str] = mapped_column(ForeignKey("conversations.key"), index=True)
    details: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    total_minor: Mapped[int] = mapped_column(Integer)
    shipping_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    payment_status: Mapped[str] = mapped_column(String(24), default="unpaid")
    version: Mapped[int] = mapped_column(Integer, default=1)
    stock_released: Mapped[bool] = mapped_column(Boolean, default=False)
    anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    expires_at: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        CheckConstraint("total_minor >= 0"),
        CheckConstraint("shipping_minor >= 0"),
    )


class Outbox(Base):
    __tablename__ = "outbound_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_key: Mapped[str] = mapped_column(String(200), unique=True)
    lane: Mapped[str] = mapped_column(String(200), index=True)
    destination: Mapped[str] = mapped_column(String(24))
    conversation_key: Mapped[str | None] = mapped_column(ForeignKey("conversations.key"))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    error: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (Index("ix_outbox_due", "status", "next_attempt", "id"),)


class OrderActivity(Base):
    __tablename__ = "order_activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    kind: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(24))
    order_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    occurred_at: Mapped[float] = mapped_column(Float)
    body: Mapped[str | None] = mapped_column(Text)
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index("ix_activity_order_id", "order_id", "id"),
        CheckConstraint("amount_minor IS NULL OR amount_minor > 0"),
    )


class Record(Base):
    """Versioned catalog snapshot, command idempotency, audits and worker heartbeat."""

    __tablename__ = "records"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Database:
    def __init__(self, settings: Settings):
        settings.prepare_local_directory()
        url = settings.database_url.get_secret_value()
        kwargs: dict[str, Any] = {"pool_pre_ping": True, "hide_parameters": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        else:
            kwargs.update(pool_size=5, max_overflow=2, connect_args={"connect_timeout": 10})
        self.engine = create_engine(url, **kwargs)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def pragmas(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def schema_ready(self) -> bool:
        with self.sessions() as session:
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))
            session.scalar(select(Inbox.id).limit(1))
            return revision == "0003"


def insert_once(session, model, values: dict, key: str):
    """Return whether a row was inserted, without relying on driver rowcount.

    Psycopg can report -1 for INSERT rowcount. RETURNING also distinguishes a
    conflict that waited for another transaction from a successful new insert.
    """
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    statement = (
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[key])
        .returning(getattr(model, key))
    )
    return session.execute(statement).scalar_one_or_none() is not None


def enqueue(session, *, key, destination, payload=None, conversation=None, order=None):
    lane = "sheets" if destination == "sheets" else f"{destination}:{conversation or order or key}"
    insert_once(
        session,
        Outbox,
        {
            "business_key": key,
            "destination": destination,
            "payload": payload or {},
            "conversation_key": conversation,
            "order_id": order,
            "lane": lane,
        },
        "business_key",
    )
