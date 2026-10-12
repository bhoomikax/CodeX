from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from app.database import Base
from app.services.evaluator import EvaluationUnavailable, validate_test_cases


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
    def test_cases_available(self) -> bool:
        """True only when the evaluator would accept this problem's cases."""
        try:
            validate_test_cases(self.test_cases)
        except EvaluationUnavailable:
            return False
        return True

    @property
    def sample_cases(self) -> list[dict]:
        """Cases flagged ``visible`` for display. Hidden cases never leave the server."""
        if not isinstance(self.test_cases, list):
            return []
        return [
            {"input": case.get("input", ""), "expected_output": case.get("expected_output", "")}
            for case in self.test_cases
            if isinstance(case, dict) and case.get("visible") is True
        ]
