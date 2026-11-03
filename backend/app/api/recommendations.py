from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from app.schemas import RecommendationResponse
from app.services.recommendation_engine import recommend

router = APIRouter(prefix="/recommend", tags=["Recommendations"])


@router.post("", response_model=RecommendationResponse)
async def get_recommendations(
    query: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    top_k: int = Form(10),
):
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

    image_bytes = None

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

        if len(image_bytes) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="Image must be 5 MB or smaller."
            )

    try:
        result = recommend(
            query=query,
            image_bytes=image_bytes,
            image_content_type=image.content_type if image else None,
            top_k=top_k,
        )
        return result

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception:
        # Log the actual exception server-side in the final implementation.
        raise HTTPException(
            status_code=500,
            detail="Recommendation generation failed."
        )