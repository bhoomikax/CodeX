from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.revision import RevisionRecommendationResponse
from app.services.revision import get_due_revisions

router = APIRouter(prefix="/revisions", tags=["Revisions"])


@router.get("/", response_model=list[RevisionRecommendationResponse])
def get_revisions(
    user_id: int = Query(gt=0, description="Learner whose due revisions should be returned"),
    db: Session = Depends(get_db),
):
    """Return due, evaluable revision problems ordered by weakest mastery first."""
    user = db.query(User.id).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return get_due_revisions(db=db, user_id=user_id)
