import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.schemas import RecommendationResponse
from app.services.recommendation_engine import recommend
from app.services.image_interpreter import interpret_image

router = APIRouter(prefix="/recommend", tags=["Recommendations"])

logger = logging.getLogger(__name__)


@router.post("", response_model=RecommendationResponse)
async def get_recommendations(
    query: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    top_k: int = Form(10),
):
    query = (query or "").strip()

    if not query and not image:
        raise HTTPException(
            status_code=400,
            detail="Provide a text query, an image, or both."
        )

    if top_k < 1 or top_k > 20:
        raise HTTPException(
            status_code=400,
            detail="top_k must be between 1 and 20."
        )

    combined_query = query

    if image:
        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=415,
                detail="Supported image formats: JPEG, PNG, WEBP."
            )

        image_bytes = await image.read()

        if not image_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty."
            )

        if len(image_bytes) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="Image must be 5 MB or smaller."
            )

        try:
            image_description = interpret_image(
                image_bytes=image_bytes,
                content_type=image.content_type,
            )

            if query:
                combined_query = f"""
User's description:
{query}

Visual interpretation of the uploaded image:
{image_description}
"""
            else:
                combined_query = f"""
The reader provided this image as inspiration for a book recommendation.

Visual interpretation:
{image_description}
"""

        except Exception as exc:
            logger.exception("Image interpretation failed")
            raise HTTPException(
                status_code=502,
                detail="Unable to interpret the uploaded image."
            ) from exc

    try:
        result = recommend(
            query=combined_query,
            top_k=top_k,
        )

        return result

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        logger.exception("Recommendation generation failed")
        raise HTTPException(
            status_code=500,
            detail="Recommendation generation failed."
        ) from exc