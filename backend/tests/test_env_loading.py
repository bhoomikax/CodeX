"""backend/.env loading: absolute path, process precedence, and test isolation.
Uses temporary .env files with fake values; never reads the real backend/.env."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["CODEX_SKIP_DOTENV"] = "1"  # never load backend/.env (real keys, database)

import app.database as database
from app.services.feedback import ai_configuration

BACKEND_DIR = Path(__file__).resolve().parent.parent
AI_NAMES = ("AI_API_KEY", "AI_API_URL", "AI_MODEL")


class EnvFileLoadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tmp.name) / ".env"
        # CRLF line endings and no trailing newline, like a file saved in a Windows editor.
        self.env_file.write_bytes(b"AI_API_URL=https://api.openai.com/v1\r\nAI_MODEL=gpt-4o-mini\r\n"
                                  b"AI_API_KEY=sk-file-fake")
        self.saved = {name: os.environ.pop(name) for name in AI_NAMES if name in os.environ}
        self.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        for name in AI_NAMES:
            os.environ.pop(name, None)
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def test_default_path_is_backend_env_regardless_of_working_directory(self):
        self.assertEqual(database.ENV_FILE, BACKEND_DIR / ".env")
        self.assertTrue(database.ENV_FILE.is_absolute())
        os.chdir(self.tmp.name)
        with patch("app.database.load_dotenv") as load:
            database.load_backend_env()
        load.assert_called_once_with(BACKEND_DIR / ".env", override=False)

    def test_ai_settings_load_from_the_env_file_from_another_directory(self):
        os.chdir(tempfile.gettempdir())
        self.assertTrue(database.load_backend_env(self.env_file))
        report = ai_configuration()
        self.assertTrue(report["enabled"])
        self.assertTrue(report["key_configured"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["endpoint"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(report["model"], "gpt-4o-mini")
        self.assertEqual(os.environ["AI_API_KEY"], "sk-file-fake")

    def test_process_environment_takes_precedence_over_the_file(self):
        os.environ["AI_API_KEY"] = "sk-process-fake"
        os.environ["AI_MODEL"] = "process-model"
        database.load_backend_env(self.env_file)
        self.assertEqual(os.environ["AI_API_KEY"], "sk-process-fake")
        self.assertEqual(os.environ["AI_MODEL"], "process-model")
        self.assertEqual(os.environ["AI_API_URL"], "https://api.openai.com/v1")

    def test_missing_file_changes_nothing(self):
        self.assertFalse(database.load_backend_env(Path(self.tmp.name) / "absent.env"))
        self.assertFalse(ai_configuration()["enabled"])


class TestIsolationTests(unittest.TestCase):
    def test_skip_switch_prevents_loading_backend_env(self):
        # A fresh interpreter importing the real module with the switch set must
        # not pick up anything from backend/.env. Only booleans are printed.
        env = {k: v for k, v in os.environ.items() if k not in AI_NAMES}
        env.update({"CODEX_SKIP_DOTENV": "1", "DATABASE_URL": "sqlite://"})
        code = ("import os, app.database; "
                f"print(any(os.getenv(n) for n in {AI_NAMES!r}), os.getenv('DATABASE_URL') == 'sqlite://')")
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertEqual(result.stdout.split(), ["False", "True"])


if __name__ == "__main__":
    unittest.main()
