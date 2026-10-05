"""Diagnostic wording is not a contract unless the visible task specifies it."""

from pathlib import Path
import unittest

from evaluate_task import matches, check_cases


class DiagnosticOracleTest(unittest.TestCase):
    def test_unspecified_wording_accepts_alternatives_but_requires_diagnostic(self):
        expected = {"exit": 2, "stderr_nonempty": True}
        check_cases([{"id": "diagnostic", "steps": [{"expect": expected}]}])
        result = {
            "exit_code": 2,
            "timeout": False,
            "output_truncated": False,
            "stdout": "",
        }
        for text in (
            "unknown id: missing",
            "no record has identifier missing",
            "operation is not supported: delete",
        ):
            self.assertTrue(matches({**result, "stderr": text}, expected, Path(".")))
        for text in ("", " \n\t"):
            self.assertFalse(matches({**result, "stderr": text}, expected, Path(".")))
        with self.assertRaisesRegex(ValueError, "invalid private expectation"):
            check_cases(
                [
                    {
                        "id": "diagnostic",
                        "steps": [{"expect": {"exit": 2, "stderr_nonempty": "true"}}],
                    }
                ]
            )
