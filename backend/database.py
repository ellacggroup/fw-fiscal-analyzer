import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Local development: sqlite:///./fw_fiscal.db (relative to backend/)
# Railway production: DATABASE_URL env var should be sqlite:////data/fw_fiscal.db
# with a persistent volume mounted at /data.  Falls back to /data/fw_fiscal.db
# when running inside a container (detected by /data directory existing).
import pathlib as _pl
_default_db = (
    "sqlite:////data/fw_fiscal.db"
    if _pl.Path("/data").exists()
    else "sqlite:///./fw_fiscal.db"
)
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AgendaUpload(Base):
    __tablename__ = "agenda_uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    meeting_date = Column(String, nullable=True)
    source_url = Column(String, nullable=True)   # populated when loaded from URL
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    item_count = Column(Integer, default=0)
    raw_text = Column(Text, nullable=True)


class AgendaItem(Base):
    __tablename__ = "agenda_items"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, nullable=False)
    item_number = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    section = Column(String, nullable=True)      # agenda section (Consent A, Zoning, etc.)
    category = Column(String, nullable=True)
    analysis = Column(JSON, nullable=True)       # merged rule-based + claude analysis
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


def _migrate_add_columns():
    """
    Add columns introduced in v3 to an existing database without dropping data.
    SQLite requires ALTER TABLE for each new column individually.
    """
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(agenda_uploads)")
            )
        }
        if "source_url" not in existing:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE agenda_uploads ADD COLUMN source_url TEXT"
                )
            )
            conn.commit()

        existing_items = {
            row[1]
            for row in conn.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(agenda_items)")
            )
        }
        if "section" not in existing_items:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE agenda_items ADD COLUMN section TEXT"
                )
            )
            conn.commit()
