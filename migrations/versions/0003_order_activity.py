"""Add private order notes, activity history and external refund ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_activity",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("actor", sa.String(24), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.Float(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint("amount_minor IS NULL OR amount_minor > 0"),
    )
    op.create_index("ix_activity_order_id", "order_activity", ["order_id", "id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE ALL ON TABLE order_activity FROM PUBLIC")
        op.execute("REVOKE ALL ON SEQUENCE order_activity_id_seq FROM PUBLIC")
        op.execute("""
            DO $$
            DECLARE role_name text;
            BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                  EXECUTE format('REVOKE ALL ON TABLE order_activity FROM %I', role_name);
                  EXECUTE format('REVOKE ALL ON SEQUENCE order_activity_id_seq FROM %I', role_name);
                END IF;
              END LOOP;
            END $$;
        """)


def downgrade():
    # Refund balances are derived from this ledger: never silently discard them.
    count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM order_activity WHERE kind = 'refund'"))
        .scalar()
    )
    if count:
        raise RuntimeError(
            "Refund ledger exists; restore/reconcile before any destructive downgrade"
        )
    op.drop_index("ix_activity_order_id", table_name="order_activity")
    op.drop_table("order_activity")
