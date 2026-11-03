import sqlite3
from contextlib import contextmanager

from app.config import DATABASE_PATH


@contextmanager
def get_db():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    conn = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )
    conn.row_factory = sqlite3.Row

    try:
        yield conn
    finally:
        conn.close()


def get_book_query():
    return """
        SELECT
            b.work_id,
            b.representative_book_id,
            b.title,
            b.author_names,
            b.description,
            b.publication_year,
            b.average_rating,
            b.ratings_count,

            be.blurb,
            be.reading_experience,
            be.themes_json,
            be.traits_json,

            be.content_embedding,
            be.experience_embedding,
            be.content_embedding_model,
            be.experience_embedding_model

        FROM books b
        JOIN book_enrichment be
            ON CAST(b.work_id AS INTEGER) = be.work_id

        WHERE be.blurb IS NOT NULL
          AND be.reading_experience IS NOT NULL
          AND TRIM(be.reading_experience) != ''
    """


def fetch_all_enriched_books():
    with get_db() as conn:
        rows = conn.execute(get_book_query()).fetchall()

    return [dict(row) for row in rows]


def fetch_book(work_id: str):
    with get_db() as conn:
        row = conn.execute(
            get_book_query() + " AND b.work_id = ?",
            (str(work_id),),
        ).fetchone()

    return dict(row) if row else None