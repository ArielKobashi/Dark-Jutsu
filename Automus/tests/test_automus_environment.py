import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import automus_environment as env


class PreflightTests(unittest.TestCase):
    def test_summary_reports_success(self):
        result = env.PreflightResult(True, ["tela 1366x768", "escala 100%"])
        self.assertEqual(result.summary(), "AMBIENTE OK | tela 1366x768 | escala 100%")

    def test_missing_totvs_is_not_ok(self):
        fake_user32 = type("User32", (), {
            "GetSystemMetrics": lambda self, index: (1366, 768)[index],
            "GetDpiForSystem": lambda self: 96,
        })()
        with patch.object(env.ctypes, "windll", type("Dll", (), {"user32": fake_user32})()), \
             patch.object(env, "enable_per_monitor_dpi_awareness"), \
             patch.object(env, "find_totvs_window", return_value=None):
            result = env.run_preflight()
        self.assertFalse(result.ok)
        self.assertFalse(result.window_found)
        self.assertIn("janela TOTVS nao encontrada", result.messages)


if __name__ == "__main__":
    unittest.main()
