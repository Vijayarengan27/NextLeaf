import csv
import json
import math
import sqlite3
import ijson

from pathlib import Path

# Input files
METADATA_PATH = Path(
    r"your-metadata-path"
)
STATS_DB_PATH = Path(
    r"your-stats-db-path"
)

# Output
OUTPUT_CSV = Path("top_5000_books.csv")
WORK_DB_PATH = Path("book_selection_work.sqlite")

# Selection criteria
TARGET_COUNT = 5000
MIN_DESCRIPTION_CHARS = 300
MIN_RATINGS_COUNT = 1000
MIN_AVERAGE_RATING = 3.5
MIN_REVIEW_COUNT = 200
MIN_USABLE_REVIEWS = 100

BATCH_SIZE = 10_000


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_authors(value):
    if isinstance(value, list):
        return ", ".join(
            str(author) for author in value if author
        )
    if isinstance(value, str):
        return value.strip()
    return ""


def is_english(language):
    language = str(language or "").strip().lower()
    return language == "eng" or language.startswith("en-")


def calculate_score(
    ratings_count,
    average_rating,
    description_chars,
    usable_review_count,
):
    """
    Rank books using popularity, review coverage,
    description quality proxy, and reader ratings.
    """
    return (
        2.0 * math.log10(ratings_count + 1)
        + 3.0 * math.log10(usable_review_count + 1)
        + min(description_chars, 3000) / 3000
        + 0.5 * (average_rating - MIN_AVERAGE_RATING)
    )


def main():
    if not METADATA_PATH.exists():
        raise FileNotFoundError(METADATA_PATH)

    if not STATS_DB_PATH.exists():
        raise FileNotFoundError(STATS_DB_PATH)

    # Use a separate working database so the review stats
    # database remains unchanged.
    if WORK_DB_PATH.exists():
        WORK_DB_PATH.unlink()

    conn = sqlite3.connect(WORK_DB_PATH)
    cur = conn.cursor()

    # Attach the existing review statistics database.
    cur.execute(
        "ATTACH DATABASE ? AS stats",
        (str(STATS_DB_PATH.resolve()),),
    )

    cur.execute("""
        CREATE TABLE candidates (
            work_id TEXT NOT NULL,
            book_id TEXT,
            title TEXT,
            authors TEXT,
            description TEXT,
            language_code TEXT,
            ratings_count INTEGER,
            average_rating REAL,
            text_reviews_count INTEGER,
            description_chars INTEGER
        )
    """)

    conn.commit()

    print("Scanning metadata and applying filters...")

    batch = []
    scanned = 0
    eligible = 0

    with open(METADATA_PATH, "rb") as f:
        records = ijson.items(
            f, "", multiple_values=True
        )

        for record in records:
            scanned += 1

            work_id = record.get("work_id")
            book_id = record.get("book_id")
            title = str(record.get("title") or "").strip()
            description = str(
                record.get("description") or ""
            ).strip()
            authors = get_authors(record.get("authors"))
            language = record.get("language_code")

            ratings_count = to_int(
                record.get("ratings_count")
            )
            average_rating = to_float(
                record.get("average_rating")
            )
            text_reviews_count = to_int(
                record.get("text_reviews_count")
            )
            description_chars = len(description)

            # Basic metadata quality filters.
            if not work_id or not book_id or not title:
                continue

            if not authors or not is_english(language):
                continue

            if description_chars < MIN_DESCRIPTION_CHARS:
                continue

            if ratings_count < MIN_RATINGS_COUNT:
                continue

            if average_rating < MIN_AVERAGE_RATING:
                continue

            batch.append((
                str(work_id),
                str(book_id),
                title,
                authors,
                description,
                str(language),
                ratings_count,
                average_rating,
                text_reviews_count,
                description_chars,
            ))

            eligible += 1

            if len(batch) >= BATCH_SIZE:
                cur.executemany("""
                    INSERT INTO candidates VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, batch)
                conn.commit()
                batch.clear()

            if scanned % 100_000 == 0:
                print(
                    f"Scanned: {scanned:,} | "
                    f"Metadata candidates: {eligible:,}"
                )

    if batch:
        cur.executemany("""
            INSERT INTO candidates VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, batch)
        conn.commit()

    print(f"Metadata records scanned: {scanned:,}")
    print(f"Metadata candidates: {eligible:,}")
    print("Joining review statistics and ranking works...")

    # The statistics are already aggregated by work_id.
    cur.execute("""
        SELECT
            c.work_id,
            c.book_id,
            c.title,
            c.authors,
            c.description,
            c.language_code,
            c.ratings_count,
            c.average_rating,
            c.text_reviews_count,
            c.description_chars,
            s.review_count,
            s.total_review_chars,
            s.usable_review_count
        FROM candidates AS c
        JOIN stats.review_stats AS s
          ON s.work_id = c.work_id
        WHERE s.review_count >= ?
          AND s.usable_review_count >= ?
    """, (MIN_REVIEW_COUNT, MIN_USABLE_REVIEWS))

    # Sort candidate editions by score, then retain only
    # the best edition for each unique work_id.
    ranked = []

    for row in cur:
        (
            work_id,
            book_id,
            title,
            authors,
            description,
            language,
            ratings_count,
            average_rating,
            text_reviews_count,
            description_chars,
            review_count,
            total_review_chars,
            usable_review_count,
        ) = row

        score = calculate_score(
            ratings_count,
            average_rating,
            description_chars,
            usable_review_count,
        )

        ranked.append((
            score,
            work_id,
            book_id,
            title,
            authors,
            description,
            language,
            ratings_count,
            average_rating,
            text_reviews_count,
            description_chars,
            review_count,
            total_review_chars,
            usable_review_count,
        ))

    ranked.sort(key=lambda row: row[0], reverse=True)

    selected = []
    seen_work_ids = set()

    for row in ranked:
        work_id = row[1]

        if work_id in seen_work_ids:
            continue

        seen_work_ids.add(work_id)
        selected.append(row)

        if len(selected) >= TARGET_COUNT:
            break

    columns = [
        "score",
        "work_id",
        "book_id",
        "title",
        "authors",
        "description",
        "language_code",
        "ratings_count",
        "average_rating",
        "text_reviews_count",
        "description_chars",
        "review_count",
        "total_review_chars",
        "usable_review_count",
    ]

    with open(
        OUTPUT_CSV, "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(columns)

        for row in selected:
            writer.writerow(row)

    print()
    print(f"Unique eligible works: {len(ranked):,}")
    print(f"Selected unique works: {len(selected):,}")
    print(f"Output saved to: {OUTPUT_CSV.resolve()}")
    print("Review statistics database was not modified.")

    conn.close()


if __name__ == "__main__":
    main()
