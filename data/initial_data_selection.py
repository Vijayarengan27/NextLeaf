import json
import sqlite3
import ijson
from pathlib import Path

METADATA_PATH = Path(r"your-metadata-path")
REVIEWS_PATH = Path(r"your-reviews-path")
DB_PATH = Path("goodreads_review_stats.sqlite")

BATCH_SIZE = 10_000
MIN_USABLE_CHARS = 100


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Reduce memory use and keep SQLite writes reasonably efficient.
cur.execute("PRAGMA journal_mode=WAL")
cur.execute("PRAGMA synchronous=NORMAL")
cur.execute("PRAGMA temp_store=FILE")
cur.execute("PRAGMA cache_size=-32768")  # About 32 MiB cache

cur.executescript("""
CREATE TABLE IF NOT EXISTS book_work (
    book_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_stats (
    work_id TEXT PRIMARY KEY,
    review_count INTEGER NOT NULL DEFAULT 0,
    total_review_chars INTEGER NOT NULL DEFAULT 0,
    usable_review_count INTEGER NOT NULL DEFAULT 0
);
""")
conn.commit()

# PASS 1: Store the ID mapping on disk.
print("Building book_id -> work_id lookup...")

with open(METADATA_PATH, "rb") as f:
    books = ijson.items(f, "", multiple_values=True)

    batch = []
    for i, book in enumerate(books, 1):
        book_id = book.get("book_id")
        work_id = book.get("work_id")

        if book_id is not None and work_id is not None:
            batch.append((str(book_id), str(work_id)))

        if len(batch) >= BATCH_SIZE:
            cur.executemany(
                "INSERT OR REPLACE INTO book_work VALUES (?, ?)", batch
            )
            conn.commit()
            batch.clear()

        if i % 500_000 == 0:
            print(f"Metadata records scanned: {i:,}")

    if batch:
        cur.executemany(
            "INSERT OR REPLACE INTO book_work VALUES (?, ?)", batch
        )
        conn.commit()

print("ID lookup ready.")

# PASS 2: Read reviews and aggregate statistics by work_id.
print("Aggregating reviews...")

# A temporary table holds only a small batch of review counts.
cur.execute("""
CREATE TEMP TABLE IF NOT EXISTS review_batch (
    work_id TEXT PRIMARY KEY,
    review_count INTEGER NOT NULL,
    total_review_chars INTEGER NOT NULL,
    usable_review_count INTEGER NOT NULL
)
""")

processed = 0
unmatched = 0
batch = {}

with open(REVIEWS_PATH, "rb") as f:
    reviews = ijson.items(f, "", multiple_values=True)

    for review in reviews:
        processed += 1
        

        book_id = review.get("book_id")
        if book_id is None:
            unmatched += 1
            continue

        # Look up this review's work_id on disk.
        row = cur.execute(
            "SELECT work_id FROM book_work WHERE book_id = ?",
            (str(book_id),)
        ).fetchone()

        if row is None:
            unmatched += 1
            continue

        work_id = row[0]
        text = (review.get("review_text") or "").strip()
        chars = len(text)
        usable = int(chars >= MIN_USABLE_CHARS)

        stats = batch.setdefault(work_id, [0, 0, 0])
        stats[0] += 1
        stats[1] += chars
        stats[2] += usable

        if len(batch) >= BATCH_SIZE:
            cur.executemany("""
                INSERT INTO review_batch VALUES (?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    review_count = review_count + excluded.review_count,
                    total_review_chars =
                        total_review_chars + excluded.total_review_chars,
                    usable_review_count =
                        usable_review_count + excluded.usable_review_count
            """, [
                (wid, values[0], values[1], values[2])
                for wid, values in batch.items()
            ])

            cur.execute("""
                INSERT INTO review_stats
                SELECT * FROM review_batch
                WHERE 1
                ON CONFLICT(work_id) DO UPDATE SET
                    review_count = review_count + excluded.review_count,
                    total_review_chars =
                        total_review_chars + excluded.total_review_chars,
                    usable_review_count =
                        usable_review_count + excluded.usable_review_count
            """)
            cur.execute("DELETE FROM review_batch")
            conn.commit()
            batch.clear()

        if processed % 500_000 == 0:
            print(
                f"Reviews processed: {processed:,} | "
                f"Unmatched: {unmatched:,}"
            )


# Flush final batch.
if batch:
    cur.executemany("""
        INSERT INTO review_batch VALUES (?, ?, ?, ?)
        ON CONFLICT(work_id) DO UPDATE SET
            review_count = review_count + excluded.review_count,
            total_review_chars = total_review_chars + excluded.total_review_chars,
            usable_review_count = usable_review_count + excluded.usable_review_count
    """, [
        (wid, values[0], values[1], values[2])
        for wid, values in batch.items()
    ])

    cur.execute("""
        INSERT INTO review_stats
        SELECT * FROM review_batch
        WHERE 1
        ON CONFLICT(work_id) DO UPDATE SET
            review_count = review_count + excluded.review_count,
            total_review_chars =
                total_review_chars + excluded.total_review_chars,
            usable_review_count =
                usable_review_count + excluded.usable_review_count
    """)
    conn.commit()

print(f"\nReviews processed: {processed:,}")
print(f"Unmatched review records: {unmatched:,}")
print("Sample work statistics:")

for row in cur.execute("""
    SELECT work_id, review_count, total_review_chars, usable_review_count
    FROM review_stats
    ORDER BY review_count DESC
    LIMIT 10
"""):
    print(row)

conn.close()
print(f"\nDone. Database saved to: {DB_PATH.resolve()}")
