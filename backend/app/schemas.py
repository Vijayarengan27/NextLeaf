from pydantic import BaseModel, Field
from typing import Optional, Any


class BookRecommendation(BaseModel):
    work_id: str
    representative_book_id: Optional[str] = None
    title: str
    author_names: Optional[str] = None

    blurb: Optional[str] = None
    reading_experience: Optional[str] = None
    themes: list[str] = Field(default_factory=list)
    traits: dict[str, float] = Field(default_factory=dict)

    publication_year: Optional[int] = None
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None

    fused_score: Optional[float] = None
    content_score: Optional[float] = None
    experience_score: Optional[float] = None
    trait_score: Optional[float] = None

    explanation: Optional[str] = None


class RecommendationResponse(BaseModel):
    query: Optional[str] = None
    interpreted_intent: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[BookRecommendation]
    total: int


class FeedbackRequest(BaseModel):
    work_id: str
    helpful: bool
    comment: Optional[str] = None