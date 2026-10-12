from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from app.database import Base


class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)
    external_id = Column(String(100), nullable=True)
    url = Column(String(500), nullable=True)
    difficulty = Column(String(20), nullable=False)
    description = Column(Text, nullable=True)
    test_cases = Column(JSON, nullable=False, default=list)
    pattern_id = Column(Integer, ForeignKey("patterns.id"), nullable=False)

    @property
    def test_cases_available(self):
        return bool(self.test_cases)
