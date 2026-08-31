"""
Database engine, session factory, and initialisation helpers.
"""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.models import Base

# Default DB path — override via DATABASE_URL env var or by calling init_db() directly.
_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "council.db"


def _enable_wal_and_fk(engine: Engine) -> None:
    """Enable WAL journal mode and foreign key enforcement for SQLite."""

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_engine(db_path: Path | str | None = None) -> Engine:
    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path}"
    engine = create_engine(url, echo=False)
    _enable_wal_and_fk(engine)
    return engine


def init_db(engine: Engine | None = None) -> Engine:
    """Create all tables and return the engine."""
    engine = engine or make_engine()
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    engine = engine or make_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Yield a database session; close on exit."""
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Seed: register the Town of Cambridge as the first target council
# ---------------------------------------------------------------------------

# The LGA is the *Town* of Cambridge — its own minutes, its own website path
# ("/About/Town-Council/") and the WA Electoral Commission all say Town. This
# row was seeded "City of Cambridge" from the start (fixed 2026-08-31), and
# because it is the council name every snapshot and rendered digest reads,
# the wrong name reached public-facing output.
CAMBRIDGE_NAME = "Town of Cambridge"


def seed_cambridge(session: Session) -> None:
    from src.models import Council

    existing = session.query(Council).filter_by(short_name="Cambridge").first()
    if existing:
        # Doubles as the migration for databases seeded before the fix: there
        # is no migration framework here, and the corpus DB lives in GCS
        # rather than in git, so correcting the constant alone would leave
        # every existing database still serving the wrong name.
        if existing.name != CAMBRIDGE_NAME:
            print(f"Correcting council name: {existing.name!r} -> {CAMBRIDGE_NAME!r}")
            existing.name = CAMBRIDGE_NAME
            session.commit()
        return

    cambridge = Council(
        name=CAMBRIDGE_NAME,
        short_name="Cambridge",
        state="WA",
        website="https://www.cambridge.wa.gov.au",
        minutes_url=(
            "https://www.cambridge.wa.gov.au/About/Town-Council/Agendas-Minutes"
        ),
    )
    session.add(cambridge)
    session.commit()
    print(f"Seeded: {CAMBRIDGE_NAME}")
