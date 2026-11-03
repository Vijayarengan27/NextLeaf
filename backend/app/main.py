import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DATABASE_PATH
from app.api import recommendations, books, feedback

app = FastAPI(
    title="NextLeaf API",
    description="Emotion-aware literary book recommendation engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_id TEXT NOT NULL,
                helpful INTEGER NOT NULL,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


@app.get("/health")
def health():
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            book_count = conn.execute(
                "SELECT COUNT(*) FROM books"
            ).fetchone()[0]

            enriched_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM book_enrichment
                WHERE blurb IS NOT NULL
                  AND reading_experience IS NOT NULL
                  AND TRIM(reading_experience) != ''
                """
            ).fetchone()[0]

        return {
            "status": "healthy",
            "database": "connected",
            "total_books": book_count,
            "enriched_books": enriched_count,
        }

    except sqlite3.Error:
        return {
            "status": "unhealthy",
            "database": "unavailable",
        }


app.include_router(recommendations.router, prefix="/api")
app.include_router(books.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")