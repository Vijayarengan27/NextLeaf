

import sqlite3
import numpy as np
import json

from sentence_transformers import SentenceTransformer


DB_PATH = "goodreads_catalog.sqlite"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 32

model = SentenceTransformer(MODEL_NAME)


# --------------------------------------------------
# Database schema management
# --------------------------------------------------

def check_columns(conn):

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(book_enrichment)")
    return {row[1] for row in cursor.fetchall()}


def add_new_columns(conn):

    columns = check_columns(conn)

    new_columns = {
        "content_embedding": "BLOB",
        "experience_embedding": "BLOB",
        "content_embedding_model": "TEXT",
        "experience_embedding_model": "TEXT"
    }

    for column, dtype in new_columns.items():

        if column not in columns:

            conn.execute(
                f"ALTER TABLE book_enrichment ADD COLUMN {column} {dtype}"
            )

    conn.commit()


# --------------------------------------------------
# Data preparation
# --------------------------------------------------

def parse_themes(themes):

    if not themes:
        return ""

    try:
        parsed = json.loads(themes)

        if isinstance(parsed, list):
            return "\n".join(f"- {item}" for item in parsed)

        if isinstance(parsed, dict):
            return "\n".join(
                f"- {key}: {value}"
                for key, value in parsed.items()
            )

    except (json.JSONDecodeError, TypeError):
        pass

    return str(themes)


def parse_traits(traits):

    if not traits:
        return {}

    try:
        parsed = json.loads(traits)

        if isinstance(parsed, dict):
            return parsed

    except (json.JSONDecodeError, TypeError):
        pass

    return {}


def describe_trait(value):

    if value is None:
        return "Unknown"

    if value < 0.2:
        return "Very low"

    elif value < 0.4:
        return "Low"

    elif value < 0.6:
        return "Moderate"

    elif value < 0.8:
        return "High"

    return "Very high"


# --------------------------------------------------
# Document construction
# --------------------------------------------------

def create_content_document(title, blurb, themes):

    return f"""
Title: {title or ""}

Book description:
{blurb or ""}

Emotional and conceptual themes:
{parse_themes(themes)}
"""


def create_experience_document(title, reading_experience):

    return f"""
Title: {title or ""}

Reading experience:
{reading_experience or ""}
""".strip()


# --------------------------------------------------
# Embedding generation
# --------------------------------------------------

def generate_embeddings(conn):

    add_new_columns(conn)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            be.work_id,
            b.title,
            be.blurb,
            be.reading_experience,
            be.themes_json,
            be.traits_json
        FROM book_enrichment be
        JOIN books b ON be.work_id = b.work_id
        WHERE be.blurb is not NULL AND
               be.reading_experience IS NOT NULL
              AND TRIM(be.reading_experience) != ''
        ORDER BY be.work_id        
    """)

    books = cursor.fetchall()

    if not books:

        print("No books need embeddings.")
        return

    content_ids = []
    content_documents = []

    experience_ids = []
    experience_documents = []

    for work_id, title, blurb, experience_blurb, themes, traits in books:

        content_document = create_content_document(
            title,
            blurb,
            themes
        )

        experience_document = create_experience_document(
            title,
            experience_blurb
        )

        content_ids.append(work_id)
        content_documents.append(content_document)

        experience_ids.append(work_id)
        experience_documents.append(experience_document)

    # Generate content embeddings

    print("Generating content embeddings...")

    content_embeddings = model.encode(
        content_documents,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    # Generate experience embeddings

    print("Generating experience embeddings...")

    experience_embeddings = model.encode(
        experience_documents,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    # Store embeddings

    for work_id, content_emb, experience_emb in zip(
        content_ids,
        content_embeddings,
        experience_embeddings
    ):

        cursor.execute("""
            UPDATE book_enrichment
            SET
                content_embedding = ?,
                content_embedding_model = ?,
                experience_embedding = ?,
                experience_embedding_model = ?
            WHERE work_id = ?
        """, (
            content_emb.astype(np.float32).tobytes(),
            MODEL_NAME,
            experience_emb.astype(np.float32).tobytes(),
            MODEL_NAME,
            work_id
        ))

    conn.commit()

    print(
        f"Successfully processed {len(books)} books."
    )


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":

    with sqlite3.connect(DB_PATH) as conn:

        generate_embeddings(conn)
