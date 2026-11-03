import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.environ.get(
    "NIRAPODNET_DB",
    "sqlite:///./nirapodnet.db"
)

# Audit fix (7): the old code always passed
# connect_args={"check_same_thread": False}, which is SQLite-only.
# A PostgreSQL URL crashed engine creation. Only SQLite gets that
# argument now; PostgreSQL gets pool_pre_ping instead. The default
# is still SQLite, and there is still no Alembic migration system:
# schema changes are create_all plus the small hand-written
# migrations in app/main.py (see _migrate_broadcast_signature).
# That limit is stated in README and docs/SECURITY.md, not hidden.
_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )


if _is_sqlite:
    # Audit fix (5): WAL mode plus a busy timeout. Several writers
    # no longer fail at once with "database is locked" as easily;
    # WAL does not remove the need for the admin backup endpoint
    # (GET /api/admin/backup), because a single .db file is still
    # a single point of failure.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
