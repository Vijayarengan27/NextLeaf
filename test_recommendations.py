
import json
import sqlite3

import numpy as np
from sentence_transformers import SentenceTransformer

from query_interpreter import interpret_query
from trait_matching import trait_match_score

DB_PATH = "data/goodreads_catalog.sqlite"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
TOP_K = 10
RRF_K = 60

model = SentenceTransformer(EMBED_MODEL)


def embed_query(text: str) -> np.ndarray:
    """Must use the same embedding model and query convention as indexing."""
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


def reciprocal_rank_fusion(ranked_ids, weight):
    """Return weighted RRF contributions keyed by work_id."""
    scores = {}
    for rank, work_id in enumerate(ranked_ids, start=1):
        scores[work_id] = weight / (RRF_K + rank)
    return scores


def recommend(query: str, limit: int = TOP_K):
    interpretation = interpret_query(query)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT
                b.work_id,
                b.title,
                be.blurb,
                be.reading_experience,
                be.themes_json,
                be.traits_json,
                be.content_embedding,
                be.experience_embedding
            FROM books b
            JOIN book_enrichment be ON be.work_id = b.work_id
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
            "Check DB_PATH and embedding generation."
        )

    # Query each embedding space independently.
    content_query = interpretation["content_query"]
    experience_query = interpretation["experience_query"]

    content_scores = {}
    experience_scores = {}
    trait_scores = {}

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

    preferences = interpretation["trait_preferences"]
    for row in rows:
        if row["traits_json"]:
            traits = json.loads(row["traits_json"])
            trait_scores[row["work_id"]] = trait_match_score(
                preferences, traits
            )

    # Convert embedding scores into rankings. Do not directly add raw
    # cosine scores from the two separate embedding spaces.
    content_ranked = [
        wid for wid, score in sorted(
            content_scores.items(), key=lambda x: x[1], reverse=True
        )
    ]
    experience_ranked = [
        wid for wid, score in sorted(
            experience_scores.items(), key=lambda x: x[1], reverse=True
        )
    ]
    trait_ranked = [
        wid for wid, score in sorted(
            trait_scores.items(),
            key=lambda x: -1 if x[1] is None else x[1],
            reverse=True,
        )
        if trait_scores[wid] is not None
    ]

    weights = {
        "content": float(interpretation["content_intent"]),
        "experience": float(interpretation["experience_intent"]),
        "traits": float(interpretation["trait_intent"]),
    }

    # Only fuse channels that actually produced usable results, then
    # renormalize their intent weights.
    channels = []
    if content_ranked and weights["content"] > 0:
        channels.append(("content", content_ranked))
    if experience_ranked and weights["experience"] > 0:
        channels.append(("experience", experience_ranked))
    if trait_ranked and weights["traits"] > 0:
        channels.append(("traits", trait_ranked))

    weight_sum = sum(weights[name] for name, _ in channels)
    if weight_sum == 0:
        raise RuntimeError("No usable retrieval channel has positive weight.")

    final_scores = {}
    for name, ranked_ids in channels:
        normalized_weight = weights[name] / weight_sum
        for wid, score in reciprocal_rank_fusion(
            ranked_ids, normalized_weight
        ).items():
            final_scores[wid] = final_scores.get(wid, 0.0) + score

    by_id = {row["work_id"]: row for row in rows}
    results = []

    for wid, fused_score in sorted(
        final_scores.items(), key=lambda item: item[1], reverse=True
    )[:limit]:
        row = by_id[wid]
        results.append({
            "work_id": wid,
            "title": row["title"],
            "final_score": round(fused_score, 6),
            "content_cosine": (
                round(content_scores[wid], 4)
                if wid in content_scores else None
            ),
            "experience_cosine": (
                round(experience_scores[wid], 4)
                if wid in experience_scores else None
            ),
            "trait_match": (
                round(trait_scores[wid], 4)
                if trait_scores.get(wid) is not None else None
            ),
            "blurb": row["blurb"],
            "reading_experience": row["reading_experience"],
        })

    return interpretation, results


if __name__ == "__main__":
    query = "I want a literary classical novel that is so easy to read and feels like a summer breeze".strip()
    interpretation, results = recommend(query)

    print("\n--- INTERPRETATION ---")
    print(json.dumps(interpretation, indent=2, ensure_ascii=False))

    print("\n--- RECOMMENDATIONS ---")
    for i, book in enumerate(results, start=1):
        print(f"\n{i}. {book['title']}")
        print(f"   Fused score:     {book['final_score']}")
        print(f"   Content cosine:  {book['content_cosine']}")
        print(f"   Experience:      {book['experience_cosine']}")
        print(f"   Trait match:     {book['trait_match']}")
        print(f"   Experience: {book['reading_experience']}")
