from fastapi import APIRouter, HTTPException

from app.database import fetch_book

router = APIRouter(prefix="/books", tags=["Books"])


@router.get("/{work_id}")
def get_book(work_id: str):
    book = fetch_book(work_id)

    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found."
        )

    import json

    try:
        book["themes"] = json.loads(book.pop("themes_json") or "[]")
    except (ValueError, TypeError):
        book["themes"] = []

    try:
        book["traits"] = json.loads(book.pop("traits_json") or "{}")
    except (ValueError, TypeError):
        book["traits"] = {}

    # Embedding blobs are internal implementation details.
    book.pop("content_embedding", None)
    book.pop("experience_embedding", None)
    book.pop("content_embedding_model", None)
    book.pop("experience_embedding_model", None)

    return book