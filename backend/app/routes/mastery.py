from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mastery import PatternMastery

router = APIRouter(prefix="/mastery", tags=["Mastery"])


@router.get("/")
def get_mastery(db: Session = Depends(get_db)):
    return db.query(PatternMastery).all()
