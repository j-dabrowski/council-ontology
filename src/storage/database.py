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
# Seed: register the City of Cambridge as the first target council
# ---------------------------------------------------------------------------


def seed_cambridge(session: Session) -> None:
    from src.models import Council

    existing = session.query(Council).filter_by(short_name="Cambridge").first()
    if existing:
        return

    cambridge = Council(
        name="City of Cambridge",
        short_name="Cambridge",
        state="WA",
        website="https://www.cambridge.wa.gov.au",
        minutes_url=(
            "https://www.cambridge.wa.gov.au/About/Town-Council/Agendas-Minutes"
        ),
    )
    session.add(cambridge)
    session.commit()
    print("Seeded: City of Cambridge")
