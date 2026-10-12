from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    code = Column(Text, nullable=True)
    language = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    evaluation_details = Column(JSON, nullable=True)
    submitted_at = Column(DateTime, server_default=func.now())
