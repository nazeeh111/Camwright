import pathlib
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js unavailable; frontend interaction checks skipped")
class FrontendTests(unittest.TestCase):
    def test_interaction_contracts(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        checked = subprocess.run(
            ["node", "--test", "tests/frontend.test.cjs"], cwd=root,
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
