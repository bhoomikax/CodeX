import os
import unittest
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, Problem, User
from app.routes.revisions import get_revisions, router
from app.services.revision import get_due_revisions


class RevisionSchedulingTests(unittest.TestCase):
    NOW = datetime(2026, 10, 12, 12, 0, 0)

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.user = User(name="Revision Learner", email="revision@example.com")
        self.other_user = User(name="Other Learner", email="revision-other@example.com")
        self.weak = Pattern(name="Weak Pattern")
        self.developing = Pattern(name="Developing Pattern")
        self.strong = Pattern(name="Strong Pattern")
        self.future = Pattern(name="Future Pattern")
        self.session.add_all(
            [self.user, self.other_user, self.weak, self.developing, self.strong, self.future]
        )
        self.session.flush()

        self.weak_easy = self._problem("Weak Easy", self.weak, "Easy")
        self.weak_hard = self._problem("Weak Hard", self.weak, "Hard")
        self.developing_easy = self._problem("Developing Easy", self.developing, "Easy")
        self.developing_medium = self._problem("Developing Medium", self.developing, "Medium")
        self.developing_hard = self._problem("Developing Hard", self.developing, "Hard")
        self.strong_easy = self._problem("Strong Easy", self.strong, "Easy")
        self.strong_hard = self._problem("Strong Hard", self.strong, "Hard")
        self._problem("Future Easy", self.future, "Easy")

        self.weak_mastery = self._mastery(self.weak, 20, self.NOW - timedelta(days=2))
        self.developing_mastery = self._mastery(
            self.developing, 55, self.NOW - timedelta(days=1)
        )
        self.strong_mastery = self._mastery(
            self.strong, 85, self.NOW - timedelta(days=3)
        )
        self.future_mastery = self._mastery(
            self.future, 10, self.NOW + timedelta(days=1)
        )
        self._mastery(self.weak, 1, self.NOW - timedelta(days=3), self.other_user.id)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _problem(self, title, pattern, difficulty, test_cases=None):
        problem = Problem(
            title=title,
            platform="Test",
            difficulty=difficulty,
            pattern_id=pattern.id,
            test_cases=test_cases if test_cases is not None else [
                {"input": "1", "expected_output": "1"}
            ],
        )
        self.session.add(problem)
        self.session.flush()
        return problem

    def _mastery(self, pattern, score, next_revision_at, user_id=None):
        mastery = PatternMastery(
            user_id=user_id or self.user.id,
            pattern_id=pattern.id,
            mastery_score=score,
            confidence_score=score,
            retention_score=score,
            total_attempts=1,
            correct_attempts=1,
            consecutive_correct=1,
            next_revision_at=next_revision_at,
        )
        self.session.add(mastery)
        self.session.flush()
        return mastery

    def test_due_revisions_prioritize_weak_patterns_and_adapt_problem_level(self):
        revisions = get_due_revisions(self.session, self.user.id, now=self.NOW)

        self.assertEqual(
            [revision.pattern_name for revision in revisions],
            ["Weak Pattern", "Developing Pattern", "Strong Pattern"],
        )
        self.assertEqual(
            [revision.problem_id for revision in revisions],
            [self.weak_easy.id, self.developing_medium.id, self.strong_hard.id],
        )
        self.assertEqual(
            [revision.due_at for revision in revisions],
            [
                self.weak_mastery.next_revision_at,
                self.developing_mastery.next_revision_at,
                self.strong_mastery.next_revision_at,
            ],
        )
        self.assertIn("below 40", revisions[0].reason)
        self.assertIn("developing", revisions[1].reason)
        self.assertIn("strong mastery", revisions[2].reason)
        self.assertGreater(revisions[0].priority, revisions[1].priority)
        self.assertGreater(revisions[1].priority, revisions[2].priority)

    def test_future_and_null_revision_dates_are_not_due(self):
        self.weak_mastery.next_revision_at = self.NOW + timedelta(seconds=1)
        self.developing_mastery.next_revision_at = None
        self.strong_mastery.next_revision_at = self.NOW + timedelta(days=1)
        self.session.commit()

        self.assertEqual(
            get_due_revisions(self.session, self.user.id, now=self.NOW),
            [],
        )

    def test_no_mastery_records_returns_empty_list(self):
        self.session.query(PatternMastery).filter_by(user_id=self.user.id).delete()
        self.session.commit()

        self.assertEqual(
            get_due_revisions(self.session, self.user.id, now=self.NOW),
            [],
        )

    def test_patterns_without_problems_with_usable_test_cases_are_skipped(self):
        self.session.query(Problem).update({Problem.test_cases: []})
        self.session.commit()

        self.assertEqual(
            get_due_revisions(self.session, self.user.id, now=self.NOW),
            [],
        )

    def test_due_pattern_without_any_problem_is_skipped(self):
        self.session.query(Problem).filter(
            Problem.pattern_id == self.weak.id
        ).delete(synchronize_session=False)
        self.session.commit()

        revisions = get_due_revisions(self.session, self.user.id, now=self.NOW)

        self.assertNotIn("Weak Pattern", [revision.pattern_name for revision in revisions])
        self.assertEqual(len(revisions), 2)

    def test_route_rejects_unknown_learner(self):
        with self.assertRaises(HTTPException) as error:
            get_revisions(user_id=99999, db=self.session)

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "User not found")

    def test_endpoint_requires_a_positive_user_id(self):
        app = FastAPI()
        app.include_router(router)
        parameters = app.openapi()["paths"]["/revisions/"]["get"]["parameters"]

        user_id_parameter = next(item for item in parameters if item["name"] == "user_id")
        self.assertTrue(user_id_parameter["required"])
        self.assertEqual(user_id_parameter["schema"]["exclusiveMinimum"], 0)
