import base64
import copy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import unittest
import zipfile

from camwright import __version__
from camwright.project import identity
from camwright.runtime import Calculator
from .test_project import example


def unpack(result):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as bundle:
        assert set(bundle.namelist()) == {"inspection.json", "inspection.html"}
        return json.loads(bundle.read("inspection.json")), bundle.read("inspection.html").decode()


class InspectionTests(unittest.TestCase):
    def test_real_completed_statuses_and_exact_inputs_are_saved_without_recalculation(self):
        # Catches recalculating, accepting caller-mutated result data, losing exact
        # inputs, or turning failure/unknown evidence into a geometry export.
        failed = {**example(), "base_radius": "18", "roller_radius": "4",
                  "maximum_pressure_slope": "0.3", "tolerance_mm": "0.02",
                  "segments": [{"span_deg": "90", "end_mm": v} for v in ["16", "16", "0", "0"]]}
        unresolved = json.loads((Path(__file__).parents[1]/"camwright/examples/unresolved.json").read_text())
        passing = example(); passing["base_radius"] = "+025.000"
        for project, status in [(passing, "pass"), (failed, "fail"), (unresolved, "unknown")]:
            with self.subTest(status=status):
                runner = Calculator()
                checked = runner.run("check", project)
                self.assertEqual(status, checked["result"]["status"])
                expected = copy.deepcopy(checked["result"])
                receipt = checked["inspection_id"]
                checked["result"]["status"] = "tampered"
                # A nonfunctional worker after completion proves saving uses the snapshot.
                runner.command = ["/no-such-camwright-worker"]
                saved = runner.save_inspection(project, identity(project), receipt)
                document, report = unpack(saved)
                self.assertEqual("camwright.inspection", document["schema"])
                self.assertEqual(1, document["version"])
                self.assertEqual(project, document["project"])
                self.assertEqual(identity(project), document["project_id"])
                self.assertEqual(expected, document["result"])
                self.assertEqual(__version__, document["implementation_version"])
                self.assertEqual({"interval_budget_per_condition": 2048, "maximum_subdivision_depth": 24}, document["check_limits"])
                self.assertEqual(project["model"], document["model"])
                self.assertEqual("mm", document["units"])
                self.assertEqual("degrees", document["angle_units"])
                self.assertTrue(document["completed_at_utc"].endswith("+00:00"))
                self.assertNotIn("preview", document)
                self.assertIn({"pass": "Pass", "fail": "Fail", "unknown": "Unresolved"}[status], report)
                for row in expected["segments"]:
                    for check in row["checks"].values():
                        if "angle_deg" in check:
                            self.assertIn(check["angle_deg"], report)
                        if "angle_interval_deg" in check:
                            for angle in check["angle_interval_deg"]:
                                self.assertIn(angle, report)
                            self.assertIn(check["reason"], report)
                if status == "fail":
                    self.assertEqual("45", expected["segments"][0]["checks"]["pressure"]["angle_deg"])
                    self.assertEqual("45/2", expected["segments"][0]["checks"]["convex_pitch"]["angle_deg"])
                runner.close()

    def test_missing_tampered_stale_and_replaced_receipts_are_refused(self):
        runner = Calculator()
        project = example()
        self.assertIn("error", runner.save_inspection(project, identity(project), "0"*32))
        first = runner.run("check", project)
        for supplied, pid, receipt in [(project, identity(project), "0"*32),
                                       (project, "0"*64, first["inspection_id"]),
                                       ({**project, "base_radius": "20"}, identity(project), first["inspection_id"])]:
            result = runner.save_inspection(supplied, pid, receipt)
            self.assertIn("error", result)
            self.assertNotIn("zip_base64", result)
        second = runner.run("check", project)
        self.assertNotEqual(first["inspection_id"], second["inspection_id"])
        self.assertIn("error", runner.save_inspection(project, identity(project), first["inspection_id"]))
        self.assertIn("zip_base64", runner.save_inspection(project, identity(project), second["inspection_id"]))
        runner.command = ["/no-such-camwright-worker"]
        self.assertIn("error", runner.run("check", project))
        self.assertIn("error", runner.save_inspection(project, identity(project), second["inspection_id"]))
        runner.close()

    def test_report_literal_text_cannot_load_scripts_or_external_resources(self):
        # The validated model rejects hostile strings, but the renderer still
        # escapes every dynamic value rather than depending on that restriction.
        from camwright.inspection import render_html
        runner = Calculator()
        project = example()
        checked = runner.run("check", project)
        doc, _ = unpack(runner.save_inspection(project, identity(project), checked["inspection_id"]))
        hostile = '</td><script src="https://attacker.invalid/x">&</script>'
        doc["project"]["base_radius"] = hostile
        doc["result"]["segments"][0]["checks"]["pressure"]["reason"] = hostile
        report = render_html(doc)

        class ReadonlyHTML(HTMLParser):
            def handle_starttag(self, tag, attrs):
                self_tags.append(tag)
                self.assert_no_remote(attrs)

            def assert_no_remote(self, attrs):
                for key, value in attrs:
                    if key in {"src", "href", "action"}:
                        assert not value or value.startswith("#"), (key, value)

        self_tags = []
        ReadonlyHTML().feed(report)
        self.assertNotIn("script", self_tags)
        self.assertNotIn("iframe", self_tags)
        self.assertIn("&lt;/td&gt;&lt;script", report)
        self.assertIn("&amp;", report)
        self.assertIn("Saved observation", report)
        self.assertIn("hardware approval", report)
        runner.close()

    def test_inspection_bounds_limit_raw_record_and_expanded_output(self):
        from camwright.inspection import build_archive
        with self.assertRaises(ValueError):
            build_archive(b" "*(512*1024+1))
        runner = Calculator()
        project = example()
        checked = runner.run("check", project)
        doc, _ = unpack(runner.save_inspection(project, identity(project), checked["inspection_id"]))
        doc["result"]["segments"][0]["checks"]["pressure"]["reason"] = "x"*300000
        snapshot = json.dumps(doc).encode()
        self.assertLess(len(snapshot), 512*1024)
        with self.assertRaises(ValueError):
            build_archive(snapshot)
        runner.close()
