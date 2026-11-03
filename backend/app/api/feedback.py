from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.schemas import FeedbackRequest

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("")
def submit_feedback(feedback: FeedbackRequest):
    with get_db() as conn:
        book = conn.execute(
            "SELECT 1 FROM books WHERE work_id = ?",
            (feedback.work_id,),
        ).fetchone()

        if not book:
            raise HTTPException(
                status_code=404,
                detail="Book not found."
            )

        conn.execute(
            """
            INSERT INTO recommendation_feedback
                (work_id, helpful, comment)
            VALUES (?, ?, ?)
            """,
            (
                feedback.work_id,
                int(feedback.helpful),
                feedback.comment,
            ),
        )

        conn.commit()

    return {"message": "Feedback received."}