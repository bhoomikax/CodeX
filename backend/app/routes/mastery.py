from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mastery import PatternMastery

router = APIRouter(prefix="/mastery", tags=["Mastery"])


@router.get("/")
def get_mastery(
    user_id: int | None = Query(default=None, gt=0, description="Only return this learner's mastery records"),
    db: Session = Depends(get_db),
):
    query = db.query(PatternMastery)
    if user_id is not None:
        query = query.filter(PatternMastery.user_id == user_id)
    return query.order_by(PatternMastery.user_id, PatternMastery.pattern_id).all()
