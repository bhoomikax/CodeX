from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class PatternMastery(Base):
    __tablename__ = "pattern_mastery"
    # One mastery row per learner and pattern. Applied to newly created
    # databases; existing tables are not altered by create_all.
    __table_args__ = (
        UniqueConstraint("user_id", "pattern_id", name="uq_pattern_mastery_user_pattern"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pattern_id = Column(Integer, ForeignKey("patterns.id"), nullable=False)

    mastery_score = Column(Float, nullable=False, default=0.0)
    confidence_score = Column(Float, nullable=False, default=0.0)
    retention_score = Column(Float, nullable=False, default=0.0)

    total_attempts = Column(Integer, nullable=False, default=0)
    correct_attempts = Column(Integer, nullable=False, default=0)
    consecutive_correct = Column(Integer, nullable=False, default=0)

    last_attempted_at = Column(DateTime, nullable=True)
    next_revision_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )
