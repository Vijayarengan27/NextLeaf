import json
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import DATABASE_PATH
from app.database import get_db
from app.services.trait_matching import trait_match_score
from app.services.query_interpreter import interpret_query


EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RRF_K = 60


@lru_cache(maxsize=1)
def get_embedding_model():
    return SentenceTransformer(EMBED_MODEL)


def embed_query(text: str) -> np.ndarray:
    model = get_embedding_model()

    vector = model.encode(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    return vector.astype(np.float32)


def unpack_embedding(blob):
    if blob is None:
        return None

    vector = np.frombuffer(blob, dtype=np.float32)

    if vector.size != 384:
        return None

    return vector


def parse_json(value, fallback):
    if not value:
        return fallback

    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback


def reciprocal_rank_fusion(ranked_ids, weight):
    scores = {}

    for rank, work_id in enumerate(ranked_ids, start=1):
        scores[work_id] = weight / (RRF_K + rank)

    return scores

def get_primary_author(author_names):
    if not author_names:
        return "Unknown author"

    return author_names.split(";")[0].strip()


def recommend(
    query: str | None = None,
    image_bytes: bytes | None = None,
    image_content_type: str | None = None,
    top_k: int = 10,
):
    if not query and not image_bytes:
        raise ValueError("Provide text or an image.")

    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")

    # 1. Interpret the request using Muse.
    interpretation = interpret_query(
        query=query,
        # image_bytes=image_bytes,
        # image_content_type=image_content_type,
    )

    # 2. Load the catalogue.
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                b.work_id,
                b.representative_book_id,
                b.title,
                b.author_names,
                b.publication_year,
                b.average_rating,
                b.ratings_count,

                be.blurb,
                be.reading_experience,
                be.themes_json,
                be.traits_json,
                be.content_embedding,
                be.experience_embedding

            FROM books b
            JOIN book_enrichment be
                ON CAST(b.work_id AS INTEGER) = be.work_id

            WHERE be.blurb IS NOT NULL
              AND be.reading_experience IS NOT NULL
              AND TRIM(be.reading_experience) != ''
              AND be.traits_json IS NOT NULL
              AND be.content_embedding IS NOT NULL
              AND be.experience_embedding IS NOT NULL
        """).fetchall()

    if not rows:
        raise RuntimeError(
            "No enriched books with both embeddings found. "
            f"Database: {DATABASE_PATH}"
        )

    # 3. Retrieve independently in each embedding space.
    content_scores = {}
    experience_scores = {}
    trait_scores = {}

    content_query = interpretation["content_query"]
    experience_query = interpretation["experience_query"]

    if content_query.strip():
        q = embed_query(content_query)

        for row in rows:
            emb = unpack_embedding(row["content_embedding"])

            if emb is not None:
                content_scores[row["work_id"]] = float(np.dot(q, emb))

    if experience_query.strip():
        q = embed_query(experience_query)

        for row in rows:
            emb = unpack_embedding(row["experience_embedding"])

            if emb is not None:
                experience_scores[row["work_id"]] = float(np.dot(q, emb))

    # 4. Calculate trait matching.
    preferences = interpretation["trait_preferences"]

    for row in rows:
        traits = parse_json(row["traits_json"], {})

        trait_scores[row["work_id"]] = trait_match_score(
            preferences,
            traits,
        )

    # 5. Convert each channel into an independent ranking.
    content_ranked = sorted(
        content_scores,
        key=content_scores.get,
        reverse=True,
    )

    experience_ranked = sorted(
        experience_scores,
        key=experience_scores.get,
        reverse=True,
    )

    trait_ranked = sorted(
        [
            wid for wid, score in trait_scores.items()
            if score is not None
        ],
        key=trait_scores.get,
        reverse=True,
    )

    # 6. Weighted reciprocal rank fusion.
    weights = {
        "content": float(interpretation["content_intent"]),
        "experience": float(interpretation["experience_intent"]),
        "traits": float(interpretation["trait_intent"]),
    }

    channels = []

    if content_ranked and weights["content"] > 0:
        channels.append(("content", content_ranked))

    if experience_ranked and weights["experience"] > 0:
        channels.append(("experience", experience_ranked))

    if trait_ranked and weights["traits"] > 0:
        channels.append(("traits", trait_ranked))

    weight_sum = sum(weights[name] for name, _ in channels)

    if weight_sum == 0:
        raise RuntimeError(
            "No usable retrieval channel has positive weight."
        )

    final_scores = {}

    for name, ranked_ids in channels:
        normalized_weight = weights[name] / weight_sum

        contributions = reciprocal_rank_fusion(
            ranked_ids,
            normalized_weight,
        )

        for wid, score in contributions.items():
            final_scores[wid] = final_scores.get(wid, 0.0) + score

    # 7. Build API response.
    by_id = {row["work_id"]: row for row in rows}
    results = []

    ranked_results = sorted(
        final_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:top_k]

    for wid, fused_score in ranked_results:
        row = by_id[wid]

        themes = parse_json(row["themes_json"], [])
        traits = parse_json(row["traits_json"], {})

        results.append({
            "work_id": str(row["work_id"]),
            "representative_book_id": (
                str(row["representative_book_id"])
                if row["representative_book_id"] is not None
                else None
            ),
            "title": row["title"],
            "author_names": get_primary_author(row["author_names"]),

            "blurb": row["blurb"],
            "reading_experience": row["reading_experience"],
            "themes": themes,
            "traits": traits,

            "publication_year": row["publication_year"],
            "average_rating": row["average_rating"],
            "ratings_count": row["ratings_count"],

            "fused_score": round(fused_score, 6),
            "content_score": (
                round(content_scores[wid], 4)
                if wid in content_scores else None
            ),
            "experience_score": (
                round(experience_scores[wid], 4)
                if wid in experience_scores else None
            ),
            "trait_score": (
                round(trait_scores[wid], 4)
                if trait_scores.get(wid) is not None else None
            ),

            "explanation": None,
        })

    return {
        "query": query,
        "interpreted_intent": interpretation,
        "recommendations": results,
        "total": len(results),
    }