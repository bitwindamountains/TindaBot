from alembic import context
from sqlalchemy import create_engine, pool, text

from tindabot.config import Settings
from tindabot.db import Base

settings = Settings()
settings.prepare_local_directory()
url = settings.database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connect_args = {"connect_timeout": 10} if url.startswith("postgresql") else {}
    engine = create_engine(
        url, poolclass=pool.NullPool, hide_parameters=True, connect_args=connect_args
    )
    with engine.connect() as connection:
        # One transaction-scoped migration lock; compatible with transaction pooling.
        with connection.begin():
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(741928105)"))
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
