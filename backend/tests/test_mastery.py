#test 

import unittest
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Pattern, PatternMastery, User
from app.services.mastery import update_mastery


class UpdateMasteryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        user = User(name="Test User", email="mastery-test@example.com")
        pattern = Pattern(name="Test Pattern")
        self.session.add_all([user, pattern])
        self.session.commit()
        self.user_id = user.id
        self.pattern_id = pattern.id

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_correct_then_incorrect_attempt_updates_mastery(self):
        after_correct = update_mastery(
            self.session,
            user_id=self.user_id,
            pattern_id=self.pattern_id,
            is_correct=True,
        )
        self.session.commit()

        self.assertEqual(after_correct.total_attempts, 1)
        self.assertEqual(after_correct.correct_attempts, 1)
        self.assertEqual(after_correct.consecutive_correct, 1)
        self.assertEqual(after_correct.mastery_score, 85)
        self.assertEqual(after_correct.confidence_score, 76.5)
        self.assertEqual(after_correct.retention_score, 85)
        self.assertIsInstance(after_correct.last_attempted_at, datetime)
        self.assertIsInstance(after_correct.next_revision_at, datetime)
        first_last_attempted_at = after_correct.last_attempted_at
        self.assertEqual(
            after_correct.next_revision_at - after_correct.last_attempted_at,
            timedelta(days=4),
        )

        after_incorrect = update_mastery(
            self.session,
            user_id=self.user_id,
            pattern_id=self.pattern_id,
            is_correct=False,
        )
        self.session.commit()

        persisted = (
            self.session.query(PatternMastery)
            .filter_by(user_id=self.user_id, pattern_id=self.pattern_id)
            .one()
        )
        self.assertEqual(after_incorrect.id, after_correct.id)
        self.assertEqual(persisted.total_attempts, 2)
        self.assertEqual(persisted.correct_attempts, 1)
        self.assertEqual(persisted.consecutive_correct, 0)
        self.assertEqual(persisted.mastery_score, 40)
        self.assertEqual(persisted.confidence_score, 36)
        self.assertEqual(persisted.retention_score, 40)
        self.assertIsInstance(persisted.last_attempted_at, datetime)
        self.assertGreater(
            persisted.last_attempted_at,
            first_last_attempted_at,
        )
        self.assertIsInstance(persisted.next_revision_at, datetime)
        self.assertEqual(
            persisted.next_revision_at - persisted.last_attempted_at,
            timedelta(days=2),
        )
