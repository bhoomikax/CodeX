from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation import recommend_problem

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
)


@router.get("/", response_model=RecommendationResponse)
def get_recommendation(
    user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    recommendation = recommend_problem(db=db, user_id=user_id)
    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail="No problems with usable test cases are available",
        )

    return recommendation