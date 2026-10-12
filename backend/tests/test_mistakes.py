import unittest
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, Problem, User
from app.routes.mistakes import get_submission_mistakes
from app.routes.submissions import create_submission
from app.schemas.submission import SubmissionCreate
from app.services.evaluator import Evaluation


class MistakeTrackingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        user = User(name="Test User", email="mistake-test@example.com")
        pattern = Pattern(name="Mistake Test Pattern")
        self.session.add_all([user, pattern])
        self.session.flush()
        problem = Problem(
            title="Mistake Test Problem",
            platform="Test",
            difficulty="Easy",
            pattern_id=pattern.id,
        )
        self.session.add(problem)
        self.session.commit()
        self.user_id = user.id
        self.problem_id = problem.id

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_incorrect_submission_creates_retrievable_mistake(self):
        self.session.query(Problem).filter_by(id=self.problem_id).update({"test_cases": [{"input": "", "expected_output": ""}]})
        with patch("app.routes.submissions.evaluate_submission", return_value=Evaluation("Wrong Answer", False, failed_test=1)), patch("app.routes.submissions.recommend_problem", return_value=None):
            submission = create_submission(
                SubmissionCreate(user_id=self.user_id, problem_id=self.problem_id, code="pass", language="python"),
                db=self.session,
            )

        mistakes = get_submission_mistakes(
            submission_id=submission["id"],
            db=self.session,
        )

        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0].submission_id, submission["id"])
        self.assertEqual(mistakes[0].category, "edge_case")
        self.assertIn("differed", mistakes[0].explanation)
        self.assertIn("Trace", mistakes[0].correction)
        mastery = self.session.query(PatternMastery).filter_by(user_id=self.user_id).one()
        self.assertEqual(mastery.total_attempts, 1)
        self.assertEqual(mastery.correct_attempts, 0)
        self.assertEqual(mastery.consecutive_correct, 0)

    def test_client_verdict_is_not_part_of_submission_input(self):
        parsed = SubmissionCreate(user_id=self.user_id, problem_id=self.problem_id,
                                  code="pass", language="python", status="Accepted", is_correct=True)
        self.assertFalse(hasattr(parsed, "is_correct"))
