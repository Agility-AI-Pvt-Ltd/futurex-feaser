from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.db_base import Base
from core.logging import register_sqlalchemy_logging

engine = create_engine(
    settings.POSTGRES_URL, 
    pool_pre_ping=True, 
    pool_recycle=300,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
)
register_sqlalchemy_logging(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_LECTURE_METADATA_ADDITIVE_COLUMNS = {
    "transcript_text": "TEXT",
    "transcript_summary": "TEXT",
    "summary_generated_at": "TIMESTAMP",
}


def _ensure_lecture_metadata_additive_columns():
    inspector = inspect(engine)
    table_name = "lecture_transcript_metadata"
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in _LECTURE_METADATA_ADDITIVE_COLUMNS.items()
        if column_name not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                )
            )


def init_db():
    
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_lecture_metadata_additive_columns()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
