"""Prevent Supabase public API roles from reading private order and queue tables."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            DO $$
            DECLARE role_name text;
            BEGIN
              FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                  EXECUTE format(
                    'REVOKE ALL ON TABLE conversations, inbound_events, products, orders, outbound_jobs, records, alembic_version FROM %I',
                    role_name);
                  EXECUTE format(
                    'REVOKE ALL ON SEQUENCE inbound_events_id_seq, outbound_jobs_id_seq FROM %I',
                    role_name);
                END IF;
              END LOOP;
            END $$;
        """)


def downgrade():
    # A rollback must never re-grant public access to personal data.
    pass
