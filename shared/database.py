"""Shared SQLAlchemy engine and schema bootstrap for all services."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from shared.config import AUTO_CREATE_SCHEMA, DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Bootstrap local schema; production deploys must run versioned migrations."""
    if not AUTO_CREATE_SCHEMA:
        return
    from shared import models  # noqa: F401
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_lock(74120931)"))
            try:
                Base.metadata.create_all(bind=connection)
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(74120931)"))
    else:
        Base.metadata.create_all(bind=engine)
