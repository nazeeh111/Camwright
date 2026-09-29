import copy
from fractions import Fraction as F
import json
import math
from pathlib import Path
import random
import unittest

from camwright import geometry as cam
from camwright.project import point


HERE = Path(__file__).parents[1] / "camwright"


def design():
    return json.loads((HERE / "examples" / "accepted.json").read_text())


def scalar(poly, u):
    return sum(coefficient * u**i for i, coefficient in enumerate(poly))


class BoundsTests(unittest.TestCase):
    def test_pi_encloses_independently_tabulated_value(self):
        lo = F("3.14159265358979323846264338327950288419716939937510")
        hi = F("3.14159265358979323846264338327950288419716939937511")
        self.assertLess(cam.PI.lo, lo)
        self.assertGreater(cam.PI.hi, hi)
        self.assertLess(cam.PI.hi - cam.PI.lo, F(1, 10**33))

    def test_power_to_bernstein_and_subdivision_with_independent_formula(self):
        rng = random.Random(711)
        for degree in range(1, 13):
            original = [F(rng.randint(-10, 10)) for _ in range(degree + 1)]
            b = cam.bernstein(list(map(cam.I.exact, original)))
            left, right = cam.split(b)
            for t in [F(0), F(1, 7), F(1, 2), F(6, 7), F(1)]:
                basis = [F(math.comb(degree, k)) * t**k * (1-t)**(degree-k) for k in range(degree + 1)]
                for coefficients, actual_u in [(b, t), (left, t/2), (right, (1+t)/2)]:
                    actual = scalar(original, actual_u)
                    self.assertEqual(actual, sum(c.lo * weight for c, weight in zip(coefficients, basis)))
                    self.assertLessEqual(min(c.lo for c in coefficients), actual)
                    self.assertGreaterEqual(max(c.hi for c in coefficients), actual)

    def test_narrow_negative_dip_between_sample_grid_points(self):
        # p(u)=(u-.501)^2 - .00000001. Grid misses its negative interval.
        coefficients = [F(501, 1000)**2 - F(1, 10**8), -F(1002, 1000), F(1)]
        self.assertTrue(all(scalar(coefficients, F(i, 100)) > 0 for i in range(101)))
        result = cam.certify(list(map(cam.I.exact, coefficients)))
        self.assertEqual("fail", result["status"])
        self.assertLessEqual(scalar(coefficients, F(result["u"])), 0)

    def test_budget_cannot_turn_undecided_inequality_into_pass(self):
        # A positive polynomial whose initial Bernstein coefficients straddle 0.
        p = list(map(cam.I.exact, [F(1, 4) + F(1, 100), -1, 1]))
        self.assertEqual("unknown", cam.certify(p, budget=1)["status"])
        self.assertEqual("pass", cam.certify(p)["status"])

    def test_interval_uncertainty_never_receives_false_pass(self):
        p = [cam.I(F(-1, 10**15), F(1, 10**15))]
        self.assertEqual("unknown", cam.certify(p, budget=1)["status"])


class GeometryTests(unittest.TestCase):
    def test_user_decision_same_motion_requires_larger_base(self):
        good = design()
        bad = copy.deepcopy(good)
        bad["base_radius"] = "20"
        self.assertEqual("pass", cam.check_design(good)["status"])
        self.assertEqual("fail", cam.check_design(bad)["status"])
        self.assertEqual("fail", cam.check_design(bad)["segments"][0]["checks"]["pressure"]["status"])

    def test_circle_export_has_known_radius_and_units(self):
        circle = design()
        circle["segments"] = [{"span_deg": "360", "end_mm": "0"}]
        checked = cam.check_design(circle)
        self.assertEqual("pass", checked["status"])
        self.assertAlmostEqual(26.565051177078, checked["pressure_angle_limit_deg_approx"])
        self.assertNotIn("maximum_pressure_angle_deg_approx", checked)
        for theta in [0, 37, 90, 181, 359]:
            p = point(circle, str(theta))
            x, y = p["cam"]
            px, py = p["pitch"]
            self.assertAlmostEqual(25, math.hypot(x, y), places=12)
            self.assertAlmostEqual(30, math.hypot(px, py), places=12)
            self.assertAlmostEqual(5, math.hypot(px-x, py-y), places=12)

    def test_polar_formula_matches_cartesian_curve_derivatives(self):
        d = design()
        _, roller, _, segments = cam.load_design(d)
        for index in [0, 2]:
            seg = segments[index]
            radius, velocity, acceleration = seg.polynomials(F(25), roller)
            for u in [F(1, 5), F(2, 5), F(4, 5)]:
                # Independent closed-form derivatives of x=R cos(theta),y=R sin(theta).
                angle = math.radians(float(seg.start_deg + seg.span_deg*u))
                f = float(u)
                h = float(seg.end_mm - seg.start_mm)
                beta = math.radians(float(seg.span_deg))
                r = 30 + float(seg.start_mm) + h*(10*f**3 - 15*f**4 + 6*f**5)
                v = h*(30*f**2 - 60*f**3 + 30*f**4)/beta
                a = h*(60*f - 180*f**2 + 120*f**3)/beta**2
                dx = v*math.cos(angle) - r*math.sin(angle)
                dy = v*math.sin(angle) + r*math.cos(angle)
                ddx = (a-r)*math.cos(angle) - 2*v*math.sin(angle)
                ddy = (a-r)*math.sin(angle) + 2*v*math.cos(angle)
                geometric_curvature = (dx*ddy-dy*ddx)/math.hypot(dx, dy)**3
                self.assertAlmostEqual((r*r+2*v*v-r*a)/(r*r+v*v)**1.5, geometric_curvature, places=13)
                self.assertAlmostEqual(float(cam.evaluate(radius, u).lo), r, places=12)
                self.assertAlmostEqual(float(cam.evaluate(velocity, u).lo), v, places=12)
                self.assertAlmostEqual(float(cam.evaluate(acceleration, u).lo), a, places=11)
                p = point(d, f"{float(seg.start_deg + seg.span_deg*u):.12f}")
                x, y = p["cam"]
                px, py = p["pitch"]
                self.assertAlmostEqual(5, math.hypot(px-x, py-y), places=12)
                self.assertAlmostEqual(0, (px-x)*dx + (py-y)*dy, places=10)


    def test_invalid_units_nonclosure_and_numeric_types(self):
        for key, value in [("units", "in"), ("base_radius", True), ("base_radius", -1),
                           ("maximum_pressure_slope", 0), ("roller_radius", float("nan"))]:
            d = design()
            d[key] = value
            with self.assertRaises(ValueError):
                cam.check_design(d)
        d = design()
        d["segments"][-1]["end_mm"] = "1"
        with self.assertRaisesRegex(ValueError, "close"):
            cam.check_design(d)


    def test_invalid_work_budget_is_rejected(self):
        for budget in [0, -1, 10001, True, 1.0]:
            with self.assertRaisesRegex(ValueError, "budget"):
                cam.check_design(design(), budget=budget)


if __name__ == "__main__":
    unittest.main()
