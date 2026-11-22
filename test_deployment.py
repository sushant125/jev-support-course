import os
import unittest
from unittest.mock import patch
from deployment import get_setting, guard_live
from support import SupportError


class DeploymentTests(unittest.TestCase):
    def test_disabled_gate(self):
        state = {}
        with self.assertRaises(SupportError):
            guard_live(state, False, now=0)
        self.assertEqual(state, {})

    def test_cooldown(self):
        state = {}
        guard_live(state, True, now=0)
        with self.assertRaises(SupportError):
            guard_live(state, True, now=4)
        guard_live(state, True, now=5)
        self.assertEqual(state["live_attempts"], 2)

    def test_session_cap(self):
        state = {}
        for i in range(10):
            guard_live(state, True, now=i * 5)
        with self.assertRaises(SupportError):
            guard_live(state, True, now=55)

    def test_environment_precedence(self):
        class Fake:
            secrets = {"ENABLE_LIVE": True}
        with patch.dict(os.environ, {"ENABLE_LIVE": "false"}):
            self.assertEqual(get_setting(Fake(), "ENABLE_LIVE", True), "false")

    def test_missing_secrets_default(self):
        class Fake:
            @property
            def secrets(self):
                raise FileNotFoundError
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_setting(Fake(), "ENABLE_LIVE", False), False)


if __name__ == "__main__":
    unittest.main()
