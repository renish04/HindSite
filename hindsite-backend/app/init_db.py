"""
One-time script to create the captured_pages table and enable pgvector.
Run from repo root: python -m app.init_db

Uses DATABASE_URL from .env. If PostgreSQL (with pgvector) runs in Docker,
point DATABASE_URL at it (e.g. postgresql://user:pass@localhost:5432/dbname)
and run this script from your host; it will create the extension and table in the container.

Use a DB user that has CREATE permission (e.g. superuser or GRANT CREATE ON SCHEMA public).
"""
import sys
from sqlalchemy import text

from app.database import Base, engine
from app.models import CapturedPage  # noqa: F401 - register model with Base


def init_db():
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        except Exception as e:
            if "vector" in str(e).lower() and ("not available" in str(e).lower() or "could not open" in str(e).lower()):
                print("pgvector extension is not installed in PostgreSQL.")
                print("Install it from: https://github.com/pgvector/pgvector#installation")
                print("Or use a database that has pgvector (e.g. Neon, Supabase).")
                sys.exit(1)
            raise
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for col_name, col_type in [
            ("summary", "TEXT"),
            ("thumbnail", "BYTEA"),
            ("topic_label", "VARCHAR(100)"),
            ("topic_confidence", "FLOAT"),
            ("topic_cluster_id", "INTEGER"),
            ("is_topic_outlier", "BOOLEAN DEFAULT FALSE"),
            ("topic_classified_at", "TIMESTAMP"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE captured_pages ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception as e:
                conn.rollback()
                if "already exists" not in str(e).lower():
                    raise
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_captured_pages_topic_label ON captured_pages(topic_label)"))
            conn.commit()
        except Exception:
            conn.rollback()
    print("Done: vector extension and captured_pages table are ready.")


if __name__ == "__main__":
    init_db()
