import csv
from fractions import Fraction as F
import io
import json
import math
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from camwright import geometry as cam
from camwright import curve_export as export


HERE = Path(__file__).parents[1] / "camwright"


def normal_design():
    return json.loads((HERE / "examples/accepted.json").read_text())


def short_design():
    d = normal_design()
    d["segments"] = [{"span_deg": "0.1", "end_mm": "0"},
                     {"span_deg": "3", "end_mm": "0.01"},
                     {"span_deg": "0.1", "end_mm": "0.01"},
                     {"span_deg": "3", "end_mm": "0"},
                     {"span_deg": "353.8", "end_mm": "0"}]
    return d


def reference(d, angle):
    """Independent scalar/cartesian coordinates, used as a numerical check."""
    start, lift = 0.0, 0.0
    if angle == 360:
        angle = 0.0
    for segment in d["segments"]:
        span, end = float(segment["span_deg"]), float(segment["end_mm"])
        if start <= angle < start+span+1e-12:
            u = (angle-start)/span
            h = end-lift
            r = float(d["base_radius"])+float(d["roller_radius"])+lift+h*(10*u**3-15*u**4+6*u**5)
            v = h*(30*u**2-60*u**3+30*u**4)/math.radians(span)
            theta = math.radians(angle)
            c,s = math.cos(theta),math.sin(theta)
            x,y = r*c,r*s
            length = math.hypot(r,v)
            roller = float(d["roller_radius"])
            return {"pitch": (x,y), "cam": (x-roller*(r*c+v*s)/length,
                                           y-roller*(r*s-v*c)/length)}
        start += span
        lift = end
    raise AssertionError("reference angle outside motion")


class ExportTests(unittest.TestCase):
    def test_endpoint_enclosures_at_exact_trig_and_square_root_values(self):
        for angle, name, expected in [(0,"cos",F(1)), (90,"cos",F(0)),
                                      (60,"cos",F(1,2)), (30,"sin",F(1,2)),
                                      (180,"sin",F(0)), (270,"sin",F(-1))]:
            cosine,sine=export.trigonometry(F(angle))
            interval=cosine if name=="cos" else sine
            self.assertLessEqual(interval.lo,expected)
            self.assertGreaterEqual(interval.hi,expected)
        root=export.sqrt_interval(cam.I.exact(2))
        self.assertLessEqual(root.lo**2,F(2))
        self.assertGreaterEqual(root.hi**2,F(2))
        self.assertEqual(cam.I.exact(6),export.sqrt_interval(cam.I.exact(36)))

    def inspect_export(self,d,tolerance):
        result=export.build_export(d,tolerance=tolerance)
        report=result["report"]
        self.assertEqual("pass",report["status"])
        files=result["files"]
        tables={name:list(csv.DictReader(io.StringIO(files[f"{name}.csv"]))) for name in ["cam","pitch"]}
        self.assertEqual(report["vertices"],len(tables["cam"]))
        cursor=F(0)
        samples_checked=0
        maximum_error=0.0
        for i,cell in enumerate(report["intervals"]):
            start,end=F(cell["start_deg_exact"]),F(cell["end_deg_exact"])
            self.assertEqual(cursor,start)
            self.assertGreater(end,start)
            cursor=end
            width=F(cell["angular_width_rad_upper"])
            self.assertGreaterEqual(width, (end-start)*cam.PI.hi/180)
            for name in ["cam","pitch"]:
                m=F(cell[f"{name}_second_derivative_bound"])
                eps=F(cell[f"{name}_endpoint_error_mm"])
                bound=F(cell[f"{name}_bound_mm"])
                self.assertLessEqual(m*width**2/8+eps,bound)
                self.assertLessEqual(bound,F(tolerance))
                row1,row2=tables[name][i],tables[name][i+1]
                self.assertEqual(start,F(row1["angle_deg_exact"]))
                self.assertEqual(end,F(row2["angle_deg_exact"]))
                left=tuple(float(row1[k]) for k in ["x_mm","y_mm"])
                right=tuple(float(row2[k]) for k in ["x_mm","y_mm"])
                for f in [0.0,0.19,0.5,0.83,1.0]:
                    angle=float(start)+(float(end)-float(start))*f
                    actual=reference(d,angle)[name]
                    linear=tuple(a+(b-a)*f for a,b in zip(left,right))
                    error=math.hypot(*(a-b for a,b in zip(actual,linear)))
                    self.assertLessEqual(error,float(bound)+1e-9)
                    maximum_error=max(maximum_error,error)
                    samples_checked+=1
        self.assertEqual(cursor,F(360))
        for name,rows in tables.items():
            self.assertEqual(rows[0]["x_mm"],rows[-1]["x_mm"])
            self.assertEqual(rows[0]["y_mm"],rows[-1]["y_mm"])
            svg=ET.fromstring(files[f"{name}.svg"])
            polyline=svg.find("{http://www.w3.org/2000/svg}polyline")
            coords=[point.split(",") for point in polyline.attrib["points"].split()]
            self.assertEqual(len(rows),len(coords))
            for row,(x,y) in zip(rows,coords):
                self.assertEqual(F(row["x_mm"]),F(x))
                self.assertEqual(-F(row["y_mm"]),F(y))
            self.assertTrue(svg.attrib["width"].endswith("mm"))
        return report,tables,samples_checked,maximum_error

    def test_serialized_normal_profile_matches_certificate_and_independent_coordinates(self):
        self.inspect_export(normal_design(),"0.01")

    def test_short_segments_not_hidden_between_a_coarse_grid(self):
        d=short_design()
        self.assertEqual("pass",cam.check_design(d)["status"])
        self.assertTrue(all(abs(math.hypot(*reference(d,angle)["cam"])-25)<1e-10
                            for angle in range(0,361,10)))
        report,tables,_,_=self.inspect_export(d,"0.001")
        angles={F(row["angle_deg_exact"]) for row in tables["cam"]}
        self.assertTrue({F("0.1"),F("3.1"),F("3.2"),F("6.2")}.issubset(angles))
        peak=next(row for row in tables["cam"] if F(row["angle_deg_exact"])==F("3.1"))
        self.assertAlmostEqual(25.01,math.hypot(float(peak["x_mm"]),float(peak["y_mm"])),places=10)
        self.assertLessEqual(F(report["maximum_cam_bound_mm"]),F("0.001"))

    def test_join_rounding_is_shared_and_circle_sagitta_is_bounded(self):
        d=normal_design()
        d["base_radius"]="25.000000000001"
        d["segments"]=[{"span_deg":"60","end_mm":"0"} for _ in range(6)]
        report,_,_,_=self.inspect_export(d,"0.01")
        for cell in report["intervals"]:
            delta=math.radians(float(F(cell["end_deg_exact"])-F(cell["start_deg_exact"])))
            self.assertLess(float(d["base_radius"])*(1-math.cos(delta/2)),float(F(cell["cam_bound_mm"])))

    def test_work_and_depth_unknown_have_no_files(self):
        d=normal_design()
        for parameters,reason in [({"budget":1},"work_budget"),
                                  ({"max_depth":1,"tolerance":"0.000001"},"depth_budget")]:
            result=export.build_export(d,**parameters)
            self.assertEqual("unknown",result["report"]["status"])
            self.assertEqual(reason,result["report"]["reason"])
            self.assertEqual({},result["files"])

    def test_invalid_budget_depth_tolerance_is_rejected(self):
        d=normal_design()
        for keyword,value in [("budget",0),("budget",True),("budget",50001),
                              ("max_depth",0),("max_depth",31),("max_depth",1.0),
                              ("tolerance","0.0000001"),("tolerance","1.0001")]:
            with self.assertRaises(ValueError):
                export.build_export(d,**{keyword:value})


if __name__=="__main__":
    unittest.main()
