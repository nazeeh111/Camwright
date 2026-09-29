import base64
import io
import json
import unittest
import zipfile

from camwright.engine import calculate
from camwright.project import identity
from .test_project import example


class EngineTests(unittest.TestCase):
    def test_export_uses_current_exact_project_and_complete_bundle(self):
        project = example()
        project["base_radius"] = "+025.000"
        result = calculate("export", project, identity(project))
        self.assertEqual("pass", result["status"])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as bundle:
            self.assertEqual({"cam.csv", "pitch.csv", "cam.svg", "pitch.svg", "checks.json", "export.json", "camwright-project.json"}, set(bundle.namelist()))
            self.assertEqual(project, json.loads(bundle.read("camwright-project.json")))
            metadata = json.loads(bundle.read("export.json"))
            self.assertEqual(identity(project), metadata["project_id"])
            self.assertEqual("mm", metadata["units"])
            self.assertEqual("pass", json.loads(bundle.read("checks.json"))["status"])

    def test_stale_identity_failure_and_unresolved_never_supply_geometry(self):
        project = example()
        stale = identity(project)
        project["base_radius"] = "20"
        for result in [calculate("export", project, stale),
                       calculate("export", project, identity(project)),
                       calculate("export", example(), identity(example()), export_budget=1)]:
            self.assertIn(result["status"], ["fail", "unknown"])
            self.assertNotIn("zip_base64", result)
        self.assertEqual("unknown", calculate("check", example(), check_budget=1)["result"]["status"])
