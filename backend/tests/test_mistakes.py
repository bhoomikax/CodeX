import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Mistake, Pattern, Problem, User
from app.routes.mistakes import get_submission_mistakes
from app.routes.submissions import create_submission
from app.schemas.submission import SubmissionCreate


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
        submission = create_submission(
            SubmissionCreate(
                user_id=self.user_id,
                problem_id=self.problem_id,
                language="text",
                status="Wrong Answer",
                is_correct=False,
            ),
            db=self.session,
        )

        mistakes = get_submission_mistakes(
            submission_id=submission.id,
            db=self.session,
        )

        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0].submission_id, submission.id)
        self.assertEqual(mistakes[0].category, "unknown")
        self.assertIn("not automatically diagnosed", mistakes[0].explanation)
        self.assertIn("edge cases", mistakes[0].correction)

    def test_incorrect_submission_accepts_explicit_feedback(self):
        submission = create_submission(
            SubmissionCreate(
                user_id=self.user_id,
                problem_id=self.problem_id,
                language="python",
                status="Wrong Answer",
                is_correct=False,
                mistake_category="edge_case",
                mistake_explanation="The empty input was not handled.",
                mistake_correction="Return the required result for empty input.",
            ),
            db=self.session,
        )

        mistake = (
            self.session.query(Mistake)
            .filter_by(submission_id=submission.id)
            .one()
        )
        self.assertEqual(mistake.category, "edge_case")
        self.assertEqual(mistake.explanation, "The empty input was not handled.")
        self.assertEqual(
            mistake.correction,
            "Return the required result for empty input.",
        )

    def test_correct_submission_cannot_include_mistake_feedback(self):
        with self.assertRaises(ValidationError):
            SubmissionCreate(
                user_id=self.user_id,
                problem_id=self.problem_id,
                language="python",
                status="Accepted",
                is_correct=True,
                mistake_category="unknown",
            )

    def test_invalid_mistake_category_is_rejected(self):
        with self.assertRaises(ValidationError):
            SubmissionCreate(
                user_id=self.user_id,
                problem_id=self.problem_id,
                language="python",
                status="Wrong Answer",
                is_correct=False,
                mistake_category="ai_detected_bug",
            )
