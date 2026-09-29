import copy
import json
from pathlib import Path
import unittest
from camwright.project import parse_json, validate_project, identity, derived, preview, point


def example():
    return json.loads((Path(__file__).parents[1]/"camwright/examples/accepted.json").read_text())


class ProjectTests(unittest.TestCase):
    def test_exact_input_strings_and_derived_values(self):
        p=example(); p["base_radius"]="+025.000"
        self.assertEqual(p,validate_project(p))
        self.assertNotEqual(identity(p),identity(example()))
        d=derived(p)
        self.assertEqual("360",d["total_deg_exact"])
        self.assertEqual("0",d["remaining_deg_exact"])
        self.assertEqual("rise",d["segments"][0]["motion"])
        self.assertEqual("120",d["segments"][1]["start_deg_exact"])

    def test_json_duplicate_unknown_and_numeric_boundaries(self):
        for raw in ['{"a":1,"a":2}', '{"x":{"a":1,"a":2}}', '{"a":NaN}', '{"a":1e999999999999}']:
            with self.assertRaises(ValueError): parse_json(raw.encode())
        for key,value in [("base_radius",0.5),("base_radius","1e100000"),("tolerance_mm","0.00001"),("version",True),("extra","x")]:
            p=example(); p[key]=value
            with self.assertRaises(ValueError): validate_project(p)
        with self.assertRaises(ValueError): parse_json(b" "*32769)
        p=example(); p["segments"][0]["extra"]=0
        with self.assertRaises(ValueError): validate_project(p)

    def test_preview_retains_short_motion_and_is_visual_only(self):
        p=example(); p["segments"]=[{"span_deg":"0.1","end_mm":"0"},{"span_deg":"3","end_mm":"0.01"},{"span_deg":"0.1","end_mm":"0.01"},{"span_deg":"3","end_mm":"0"},{"span_deg":"353.8","end_mm":"0"}]
        result=preview(p)
        self.assertTrue(result["visual_only"])
        self.assertTrue(any(abs(x["angle_deg"]-3.1)<1e-12 for x in result["points"]))
        peak=point(p,"3.1")
        self.assertAlmostEqual(.01,peak["lift_mm"])
        self.assertAlmostEqual(5,((peak["pitch"][0]-peak["cam"][0])**2+(peak["pitch"][1]-peak["cam"][1])**2)**.5)

    def test_draft_totals_are_exact_without_claiming_closed_geometry(self):
        p=example(); p["segments"][0]["span_deg"]="150"
        validate_project(p,require_closed=False)
        d=derived(p,require_closed=False)
        self.assertEqual("390",d["total_deg_exact"])
        self.assertEqual("-30",d["remaining_deg_exact"])
        self.assertEqual("150",d["segments"][1]["start_deg_exact"])
        with self.assertRaises(ValueError): validate_project(p)
        p["segments"][0]["span_deg"]="1e100000"
        with self.assertRaises(ValueError): validate_project(p,require_closed=False)
