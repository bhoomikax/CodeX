import unittest
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, Problem, Submission, User
from app.services.recommendation import recommend_problem


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        user = User(name="Recommendation User", email="recommend@example.com")
        weak_pattern = Pattern(name="Weak Pattern")
        strong_pattern = Pattern(name="Strong Pattern")
        self.session.add_all([user, weak_pattern, strong_pattern])
        self.session.flush()
        self.user_id = user.id
        self.weak_pattern_id = weak_pattern.id
        self.strong_pattern_id = strong_pattern.id

        self.weak_easy = self._problem("Weak Easy", "Easy", weak_pattern.id)
        self.weak_easy_followup = self._problem(
            "Weak Easy Follow-up",
            "Easy",
            weak_pattern.id,
        )
        self.weak_hard = self._problem("Weak Hard", "Hard", weak_pattern.id)
        self.strong_easy = self._problem("Strong Easy", "Easy", strong_pattern.id)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _problem(self, title, difficulty, pattern_id):
        problem = Problem(
            title=title,
            platform="Test",
            difficulty=difficulty,
            pattern_id=pattern_id,
            test_cases=[{"input": "", "expected_output": ""}],
        )
        self.session.add(problem)
        self.session.flush()
        return problem

    def _mastery(self, pattern_id, score):
        self.session.add(
            PatternMastery(
                user_id=self.user_id,
                pattern_id=pattern_id,
                mastery_score=score,
                confidence_score=score,
                retention_score=score,
                total_attempts=1,
                correct_attempts=1,
                consecutive_correct=1,
            )
        )
        self.session.commit()

    def test_low_mastery_prioritizes_foundational_problem(self):
        self._mastery(self.weak_pattern_id, 25)
        self._mastery(self.strong_pattern_id, 80)

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.problem_id, self.weak_easy.id)
        self.assertEqual(recommendation.title, "Weak Easy")
        self.assertEqual(recommendation.difficulty, "Easy")
        self.assertIn("below 40", recommendation.reason)

    def test_high_mastery_recommends_harder_unsolved_problem(self):
        self._mastery(self.weak_pattern_id, 85)

        self.session.add(
            Submission(
                user_id=self.user_id,
                problem_id=self.weak_easy.id,
                language="text",
                status="Accepted",
                is_correct=True,
            )
        )
        self.session.commit()

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.problem_id, self.weak_hard.id)
        self.assertEqual(recommendation.difficulty, "Hard")
        self.assertIn("harder", recommendation.reason)

    def test_medium_mastery_recommends_similar_difficulty(self):
        self._mastery(self.weak_pattern_id, 55)
        self.session.add(
            Submission(
                user_id=self.user_id,
                problem_id=self.weak_easy.id,
                language="text",
                status="Accepted",
                is_correct=True,
            )
        )
        self.session.commit()

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.problem_id, self.weak_easy_followup.id)
        self.assertEqual(recommendation.difficulty, "Easy")
        self.assertIn("developing mastery", recommendation.reason)

    def test_no_mastery_recommends_available_starter_problem(self):
        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.problem_id, self.weak_easy.id)
        self.assertEqual(recommendation.difficulty, "Easy")
        self.assertIn("Start with", recommendation.reason)

    def test_attempt_history_identifies_weak_pattern_without_mastery_record(self):
        self._mastery(self.strong_pattern_id, 80)
        self.session.add(
            Submission(
                user_id=self.user_id,
                problem_id=self.weak_easy.id,
                language="python",
                status="Wrong Answer",
                is_correct=False,
            )
        )
        self.session.commit()

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.pattern, "Weak Pattern")
        self.assertEqual(recommendation.problem_id, self.weak_easy_followup.id)
        self.assertIn("0% correct", recommendation.reason)

    def test_incorrectly_attempted_problem_is_avoided_when_an_alternative_exists(self):
        self._mastery(self.weak_pattern_id, 25)
        self.session.add(
            Submission(
                user_id=self.user_id,
                problem_id=self.weak_easy.id,
                language="python",
                status="Wrong Answer",
                is_correct=False,
            )
        )
        self.session.commit()

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertEqual(recommendation.problem_id, self.weak_easy_followup.id)
        self.assertNotEqual(recommendation.problem_id, self.weak_easy.id)
        self.assertNotIn("All available problems", recommendation.reason)

    def test_problems_without_runnable_cases_are_never_recommended(self):
        self.session.add(Problem(title="No cases", platform="Test", difficulty="Easy",
                                 pattern_id=self.weak_pattern_id, test_cases=[]))
        self.session.add(Problem(title="Broken cases", platform="Test", difficulty="Easy",
                                 pattern_id=self.weak_pattern_id, test_cases=[{"input": 1}]))
        for problem in self.session.query(Problem).all():
            problem.test_cases = problem.test_cases if problem.title in ("No cases", "Broken cases") else []
        self.session.commit()

        self.assertIsNone(recommend_problem(self.session, self.user_id))

    def test_completed_problem_is_excluded(self):
        self.session.add(
            Submission(
                user_id=self.user_id,
                problem_id=self.weak_easy.id,
                language="text",
                status="Accepted",
                is_correct=True,
            )
        )
        self.session.commit()

        recommendation = recommend_problem(self.session, self.user_id)

        self.assertNotEqual(recommendation.problem_id, self.weak_easy.id)
