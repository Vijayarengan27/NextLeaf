"""
Build a local SQLite catalog from the Goodreads data files.

Inputs (adjust DATA_DIR if yours differs):
  goodreads_books.json
  goodreads_book_authors.json.gz
  goodreads_reviews_dedup.json
  goodreads_review_stats_test4.sqlite (existing review aggregates)

Outputs:
  goodreads_catalog.sqlite
  catalog_build_work.sqlite (temporary; retained if the run fails)

This script does not download or redistribute dataset contents. Check dataset terms
before sharing any derived data.
"""
from __future__ import annotations

import gzip
import json
import math
import random
import sqlite3
from pathlib import Path

import ijson

DATA_DIR = Path(r"your\data\path")  # <- add your data directory path here
PROJECT_DIR = Path(__file__).resolve().parent

BOOKS_FILE = DATA_DIR / "goodreads_books.json/goodreads_books.json"
AUTHORS_FILE = DATA_DIR / "goodreads_book_authors.json.gz"
REVIEWS_FILE = DATA_DIR / "goodreads_reviews_dedup.json/goodreads_reviews_dedup.json"
REVIEW_STATS_DB = PROJECT_DIR / "goodreads_review_stats.sqlite"
OUTPUT_DB = PROJECT_DIR / "goodreads_catalog.sqlite"
WORK_DB = PROJECT_DIR / "catalog_build_work.sqlite"

TARGET_WORKS = 5_000  # <- change the number of works you want here
MIN_DESCRIPTION_CHARS = 300
MIN_RATINGS_COUNT = 1_000
MIN_AVERAGE_RATING = 3.5
MIN_REVIEW_COUNT = 200
MIN_USABLE_REVIEWS = 100
MIN_SAMPLE_REVIEW_CHARS = 200
MAX_REVIEWS_PER_RATING = 4
RANDOM_SEED = 42
BATCH_SIZE = 5_000


def open_binary(path: Path):
    return gzip.open(path, "rb") if path.suffix.lower() == ".gz" else path.open("rb")


def records(path: Path):
    # The Goodreads files contain concatenated top-level JSON objects, not one array.
    with open_binary(path) as f:
        yield from ijson.items(f, "", multiple_values=True)


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


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def create_work_db():
    # This is a dedicated temporary DB; do not touch the existing review stats DB.
    if WORK_DB.exists():
        WORK_DB.unlink()
    conn = sqlite3.connect(WORK_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE candidates (
            book_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            title TEXT,
            description TEXT,
            language_code TEXT,
            num_pages INTEGER,
            publication_year INTEGER,
            publisher TEXT,
            average_rating REAL,
            ratings_count INTEGER,
            text_reviews_count INTEGER,
            author_ids_json TEXT,
            shelves_json TEXT,
            series_json TEXT
        );
        CREATE INDEX idx_candidates_work_id ON candidates(work_id);
        CREATE TABLE author_names (
            author_id TEXT PRIMARY KEY,
            name TEXT
        );
    """)
    return conn


def main():
    for path in (BOOKS_FILE, AUTHORS_FILE, REVIEWS_FILE, REVIEW_STATS_DB):
        if not path.is_file():
            raise FileNotFoundError(
                f"Required input not found: {path}\n"
                "Check DATA_DIR and filenames before running again."
            )

    # Protect an existing output by requiring the user to rename/remove it manually.
    if OUTPUT_DB.exists():
        raise FileExistsError(
            f"{OUTPUT_DB} already exists. Rename it or move it before rerunning; "
            "the script will not overwrite an existing catalog."
        )

    conn = create_work_db()
    print("Step 1/4: scanning book metadata...")
    scanned = 0
    retained = 0
    batch = []

    for book in records(BOOKS_FILE):
        scanned += 1
        book_id = str(book.get("book_id") or "").strip()
        work_id = str(book.get("work_id") or "").strip()
        if not book_id or not work_id:
            continue

        language = str(book.get("language_code") or "").strip().lower()
        if language != "eng" and not language.startswith("en-"):
            continue

        description = str(book.get("description") or "").strip()
        ratings_count = to_int(book.get("ratings_count"))
        average_rating = to_float(book.get("average_rating"))
        if (
            len(description) < MIN_DESCRIPTION_CHARS
            or ratings_count < MIN_RATINGS_COUNT
            or average_rating < MIN_AVERAGE_RATING
        ):
            continue

        authors = book.get("authors") or []
        author_ids = [
            str(a["author_id"])
            for a in authors
            if isinstance(a, dict) and a.get("author_id") is not None
        ]
        pages = to_int(book.get("num_pages"), 0) or None
        year = to_int(book.get("publication_year"), 0) or None

        batch.append((
            book_id, work_id, book.get("title"), description, language,
            pages, year, book.get("publisher"), average_rating, ratings_count,
            to_int(book.get("text_reviews_count")), json_dump(author_ids),
            json_dump(book.get("popular_shelves") or []),
            json_dump(book.get("series") or []),
        ))
        if len(batch) >= BATCH_SIZE:
            conn.executemany("""
                INSERT OR REPLACE INTO candidates VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            retained += len(batch)
            batch.clear()

        if scanned % 250_000 == 0:
            print(f"  scanned {scanned:,}; retained {retained + len(batch):,}")

    if batch:
        conn.executemany("""
            INSERT OR REPLACE INTO candidates VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        retained += len(batch)
    print(f"  complete: {scanned:,} metadata records scanned; {retained:,} candidate editions")

    print("Step 2/4: resolving author names...")
    # Resolve only author IDs referenced by the filtered candidate editions.
    # A SQLite join table avoids keeping millions of IDs in a Python set.
    conn.execute("CREATE TABLE needed_author_ids (author_id TEXT PRIMARY KEY)")
    for (ids_json,) in conn.execute("SELECT author_ids_json FROM candidates"):
        for author_id in json.loads(ids_json or "[]"):
            conn.execute(
                "INSERT OR IGNORE INTO needed_author_ids(author_id) VALUES (?)",
                (author_id,),
            )
    conn.commit()
    needed_count = conn.execute("SELECT COUNT(*) FROM needed_author_ids").fetchone()[0]
    found = 0
    for author in records(AUTHORS_FILE):
        aid = author.get("author_id")
        name = author.get("name")
        if aid is None or name is None:
            continue
        aid = str(aid)
        exists = conn.execute(
            "SELECT 1 FROM needed_author_ids WHERE author_id = ?", (aid,)
        ).fetchone()
        if exists:
            conn.execute(
                "INSERT OR REPLACE INTO author_names(author_id, name) VALUES (?, ?)",
                (aid, str(name).strip()),
            )
            found += 1
            conn.execute("DELETE FROM needed_author_ids WHERE author_id = ?", (aid,))
        if found and found % 50_000 == 0:
            conn.commit()
            print(f"  resolved {found:,} / {needed_count:,}")
        if conn.execute("SELECT COUNT(*) FROM needed_author_ids").fetchone()[0] == 0:
            break
    conn.commit()
    print(f"  resolved {found:,} author IDs ({needed_count - found:,} unresolved)")

    print("Step 3/4: selecting unique works...")
    # Check the aggregate DB schema explicitly instead of silently assuming it.
    stats_tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM stats.sqlite_master WHERE type='table'"
        )
    } if False else set()
    conn.execute("ATTACH DATABASE ? AS stats", (str(REVIEW_STATS_DB.resolve()),))
    stats_columns = {
        row[1] for row in conn.execute("PRAGMA stats.table_info(review_stats)")
    }
    required_stats = {"work_id", "review_count", "total_review_chars", "usable_review_count"}
    if not required_stats.issubset(stats_columns):
        raise RuntimeError(
            "review_stats table schema does not match expectations. "
            f"Expected columns {sorted(required_stats)}, found {sorted(stats_columns)}."
        )

    rows = conn.execute("""
        SELECT c.book_id, c.work_id, c.title, c.description, c.language_code,
               c.num_pages, c.publication_year, c.publisher, c.average_rating,
               c.ratings_count, c.text_reviews_count, c.author_ids_json,
               c.shelves_json, c.series_json,
               s.review_count, s.total_review_chars, s.usable_review_count
        FROM candidates AS c
        JOIN stats.review_stats AS s ON s.work_id = c.work_id
        WHERE s.review_count >= ? AND s.usable_review_count >= ?
    """, (MIN_REVIEW_COUNT, MIN_USABLE_REVIEWS)).fetchall()

    # Choose the highest-scoring eligible edition per work.
    best = {}
    for row in rows:
        (book_id, work_id, title, description, language, pages, year, publisher,
         avg_rating, ratings_count, text_reviews_count, author_ids_json,
         shelves_json, series_json, review_count, total_chars, usable_count) = row
        score = (
            2.0 * math.log10(ratings_count + 1)
            + 3.0 * math.log10(usable_count + 1)
            + min(len(description or ""), 3000) / 3000
            + 0.5 * (avg_rating - MIN_AVERAGE_RATING)
        )
        current = best.get(work_id)
        if current is None or score > current["score"]:
            best[work_id] = {
                "book_id": book_id, "work_id": work_id, "title": title,
                "description": description, "language": language, "pages": pages,
                "year": year, "publisher": publisher, "avg_rating": avg_rating,
                "ratings_count": ratings_count, "text_reviews_count": text_reviews_count,
                "author_ids_json": author_ids_json, "shelves_json": shelves_json,
                "series_json": series_json, "review_count": review_count,
                "total_chars": total_chars, "usable_count": usable_count, "score": score,
            }

    selected = sorted(best.values(), key=lambda x: x["score"], reverse=True)[:TARGET_WORKS]
    selected_work_ids = {x["work_id"] for x in selected}
    print(f"  eligible works: {len(best):,}; selected works: {len(selected):,}")

    # Build a lookup for all editions belonging to the selected works.
    # This ensures reviews attached to alternate editions can be retained.
    conn.execute("CREATE TABLE selected_work_ids (work_id TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO selected_work_ids(work_id) VALUES (?)",
        [(wid,) for wid in selected_work_ids],
    )
    conn.execute("""
        CREATE TABLE selected_book_map (
            book_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO selected_book_map(book_id, work_id)
        SELECT c.book_id, c.work_id
        FROM candidates c
        JOIN selected_work_ids s ON s.work_id = c.work_id
    """)
    conn.commit()

    out = sqlite3.connect(OUTPUT_DB)
    out.execute("PRAGMA journal_mode=WAL")
    out.execute("PRAGMA synchronous=NORMAL")
    out.execute("PRAGMA foreign_keys=ON")
    out.executescript("""
        CREATE TABLE books (
            work_id TEXT PRIMARY KEY,
            representative_book_id TEXT NOT NULL,
            title TEXT,
            author_names TEXT,
            author_ids_json TEXT,
            description TEXT,
            language_code TEXT,
            num_pages INTEGER,
            publication_year INTEGER,
            publisher TEXT,
            average_rating REAL,
            ratings_count INTEGER,
            text_reviews_count INTEGER,
            review_count INTEGER,
            total_review_chars INTEGER,
            usable_review_count INTEGER,
            selection_score REAL,
            popular_shelves_json TEXT,
            series_json TEXT
        );
        CREATE TABLE reviews (
            review_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL REFERENCES books(work_id),
            source_book_id TEXT,
            rating INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            review_chars INTEGER NOT NULL,
            date_added TEXT,
            n_votes INTEGER,
            sample_slot INTEGER NOT NULL,
            UNIQUE(work_id, rating, sample_slot)
        );
        CREATE INDEX idx_reviews_work_rating ON reviews(work_id, rating);
        CREATE INDEX idx_reviews_work ON reviews(work_id);
    """)

    book_rows = []
    for item in selected:
        author_ids = json.loads(item["author_ids_json"] or "[]")
        names = []
        for aid in author_ids:
            name_row = conn.execute(
                "SELECT name FROM author_names WHERE author_id = ?", (aid,)
            ).fetchone()
            if name_row and name_row[0] and name_row[0] not in names:
                names.append(name_row[0])
        book_rows.append((
            item["work_id"], item["book_id"], item["title"], "; ".join(names),
            item["author_ids_json"], item["description"], item["language"], item["pages"],
            item["year"], item["publisher"], item["avg_rating"], item["ratings_count"],
            item["text_reviews_count"], item["review_count"], item["total_chars"],
            item["usable_count"], item["score"], item["shelves_json"], item["series_json"],
        ))
    out.executemany("INSERT INTO books VALUES (" + ",".join(["?"] * 19) + ")", book_rows)
    out.commit()

    print("Step 4/4: streaming reviews and maintaining a bounded sample...")
    rng = random.Random(RANDOM_SEED)
    # At most K review records per (work, rating) are held in SQLite, not RAM.
    # Per-bucket reservoir replacement is applied as reviews stream through.
    seen = {}
    review_scan_count = 0
    eligible_count = 0
    upsert_sql = """
        INSERT OR REPLACE INTO reviews
        (review_id, work_id, source_book_id, rating, review_text, review_chars,
         date_added, n_votes, sample_slot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for review in records(REVIEWS_FILE):
        review_scan_count += 1
        source_book_id = str(review.get("book_id") or "")
        map_row = conn.execute(
            "SELECT work_id FROM selected_book_map WHERE book_id = ?",
            (source_book_id,),
        ).fetchone()
        if not map_row:
            continue
        work_id = map_row[0]
        rating = to_int(review.get("rating"), 0)
        if rating < 1 or rating > 5:
            continue
        text = str(review.get("review_text") or "").strip()
        if len(text) < MIN_SAMPLE_REVIEW_CHARS:
            continue
        review_id = str(review.get("review_id") or "")
        if not review_id:
            continue

        eligible_count += 1
        key = (work_id, rating)
        seen[key] = seen.get(key, 0) + 1
        count = seen[key]
        k = MAX_REVIEWS_PER_RATING
        if count <= k:
            slot = count - 1
        else:
            replacement = rng.randrange(count)
            if replacement >= k:
                continue
            slot = replacement

        out.execute(upsert_sql, (
            review_id, work_id, source_book_id, rating, text, len(text),
            review.get("date_added"), to_int(review.get("n_votes"), 0), slot,
        ))
        if eligible_count % BATCH_SIZE == 0:
            out.commit()
        if review_scan_count % 1_000_000 == 0:
            out.commit()
            print(
                f"  scanned {review_scan_count:,} reviews; "
                f"{eligible_count:,} substantive reviews matched selected works"
            )

    out.commit()
    book_count = out.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    review_count = out.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    no_author_count = out.execute(
        "SELECT COUNT(*) FROM books WHERE author_names IS NULL OR author_names = ''"
    ).fetchone()[0]
    print("\nFinished successfully.")
    print(f"Output database: {OUTPUT_DB}")
    print(f"Books: {book_count:,}")
    print(f"Sampled reviews: {review_count:,}")
    print(f"Reviews scanned: {review_scan_count:,}")
    print(f"Substantive reviews matching selected works: {eligible_count:,}")
    print(f"Books without resolved author names: {no_author_count:,}")
    print("Review cap: up to 4 per rating (1-5), minimum 200 characters.")
    out.close()
    conn.close()
    # Leave WORK_DB in place on errors for diagnosis; remove after success.
    try:
        WORK_DB.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
