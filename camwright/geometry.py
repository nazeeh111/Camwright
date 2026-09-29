"""Continuous geometric checks for convex in-line roller cams.

Decimal inputs are rational; pi is enclosed using Machin's formula and an
alternating-series remainder. Export bounds are implemented in curve_export.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
import math
import re


@dataclass(frozen=True)
class I:
    lo: F
    hi: F

    @classmethod
    def exact(cls, value):
        value = F(value)
        return cls(value, value)

    def __add__(self, other):
        other = as_interval(other)
        return I(self.lo + other.lo, self.hi + other.hi)

    __radd__ = __add__

    def __neg__(self):
        return I(-self.hi, -self.lo)

    def __sub__(self, other):
        return self + -as_interval(other)

    def __rsub__(self, other):
        return as_interval(other) + -self

    def __mul__(self, other):
        other = as_interval(other)
        products = [a * b for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return I(min(products), max(products))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = as_interval(other)
        if other.lo <= 0 <= other.hi:
            raise ValueError("division interval contains zero")
        return self * I(1 / other.hi, 1 / other.lo)


def as_interval(value):
    return value if isinstance(value, I) else I.exact(value)


def atan_reciprocal(q, terms=24):
    """Exact enclosure from two successive alternating partial sums."""
    total = sum((F((-1) ** k, (2 * k + 1) * q ** (2 * k + 1)) for k in range(terms)), F(0))
    following = total + F((-1) ** terms, (2 * terms + 1) * q ** (2 * terms + 1))
    return I(min(total, following), max(total, following))


def decimal_enclosure(value, digits=34):
    denominator = 10**digits
    return I(F(math.floor(value.lo * denominator), denominator),
             F(math.ceil(value.hi * denominator), denominator))


PI = decimal_enclosure(16 * atan_reciprocal(5) - 4 * atan_reciprocal(239))
DEGREES_PER_RADIAN = I.exact(180) / PI


def add(a, b):
    return [(a[i] if i < len(a) else I.exact(0)) + (b[i] if i < len(b) else I.exact(0))
            for i in range(max(len(a), len(b)))]


def scale(a, factor):
    return [c * factor for c in a]


def mul(a, b):
    result = [I.exact(0) for _ in range(len(a) + len(b) - 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            result[i + j] = result[i + j] + x * y
    return result


def derivative(a):
    return [a[i] * i for i in range(1, len(a))] or [I.exact(0)]


def evaluate(a, t):
    result = I.exact(0)
    for c in reversed(a):
        result = result * t + c
    return result


def bernstein(a):
    n = len(a) - 1
    return [sum((a[i] * F(math.comb(k, i), math.comb(n, i)) for i in range(k + 1)), I.exact(0))
            for k in range(n + 1)]


def split(b):
    rows = [b]
    while len(rows[-1]) > 1:
        rows.append([(x + y) * F(1, 2) for x, y in zip(rows[-1], rows[-1][1:])])
    return [row[0] for row in rows], [row[-1] for row in reversed(rows)]


def certify(a, *, strict=True, budget=4096, max_depth=24):
    """Prove positivity on [0,1], provide a negative witness, or return unknown.

    Bounds follow from the convex-hull property of the Bernstein basis. Exact
    rational interval arithmetic includes coefficient and pi uncertainty.
    """
    stack = [(bernstein(a), F(0), F(1), 0)]
    visited = 0
    leaves = []
    while stack:
        b, lo, hi, depth = stack.pop()
        visited += 1
        for t in (lo, (lo + hi) / 2, hi):
            v = evaluate(a, t)
            if v.hi < 0 or (strict and v.hi == 0):
                return {"status": "fail", "u": str(t), "value": [str(v.lo), str(v.hi)], "boxes": visited}
        lower = min(c.lo for c in b)
        if lower > 0 or (not strict and lower >= 0):
            leaves.append([str(lo), str(hi), str(lower)])
            continue
        if visited >= budget or depth >= max_depth:
            return {"status": "unknown", "interval": [str(lo), str(hi)], "boxes": visited}
        left, right = split(b)
        mid = (lo + hi) / 2
        stack.extend([(right, mid, hi, depth + 1), (left, lo, mid, depth + 1)])
    return {"status": "pass", "boxes": visited, "leaves": leaves}


def rational(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a fixed-decimal string or integer")
    if isinstance(value, int):
        if abs(value) > 100000:
            raise ValueError(f"{label} exceeds input limits")
        return F(value)
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a fixed-decimal string or integer")
    if len(value) > 32:
        raise ValueError(f"{label} is too long")
    if re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", value) is None:
        raise ValueError(f"{label} requires fixed-decimal notation")
    sign = -1 if value.startswith("-") else 1
    whole, _, decimal = value.lstrip("+-").partition(".")
    whole = whole.lstrip("0") or "0"
    decimal = decimal.rstrip("0")
    if (len(decimal) > 12 or len(whole) > 6 or
            (len(whole) == 6 and whole > "100000") or
            (whole == "100000" and decimal)):
        raise ValueError(f"{label} exceeds input limits")
    # Both integer conversion and exponentiation are now bounded: at most
    # eighteen numerator digits and twelve decimal places reach Fraction.
    return F(sign * int(whole + decimal), 10**len(decimal))


@dataclass(frozen=True)
class Segment:
    start_deg: F
    span_deg: F
    start_mm: F
    end_mm: F

    def polynomials(self, base, roller):
        # 3-4-5 motion: s(u) = s0 + h(10u^3 - 15u^4 + 6u^5).
        h = self.end_mm - self.start_mm
        s = list(map(I.exact, [self.start_mm, 0, 0, 10 * h, -15 * h, 6 * h]))
        radius = add(s, [I.exact(base + roller)])
        angle_factor = DEGREES_PER_RADIAN / self.span_deg
        velocity = scale(derivative(s), angle_factor)
        acceleration = scale(derivative(velocity), angle_factor)
        return radius, velocity, acceleration


def load_design(data):
    if not isinstance(data, dict):
        raise ValueError("design must be an object")
    if data.get("units") != "mm":
        raise ValueError("dimensions require millimetres")
    base = rational(data["base_radius"], "base_radius")
    roller = rational(data["roller_radius"], "roller_radius")
    slope = rational(data["maximum_pressure_slope"], "maximum_pressure_slope")
    if base <= 0 or roller <= 0 or not 0 < slope <= 1:
        raise ValueError("positive radii and a pressure slope in (0,1] are required")
    raw = data["segments"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 12:
        raise ValueError("one to twelve segments are required")
    start = F(0)
    height = F(0)
    segments = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError("segment must be an object")
        span = rational(row["span_deg"], f"segment {i} angle")
        end = rational(row["end_mm"], f"segment {i} end")
        if span <= 0 or end < 0:
            raise ValueError("segment angles must be positive and lift nonnegative")
        segments.append(Segment(start, span, height, end))
        start += span
        height = end
    if start != 360 or height != 0:
        raise ValueError("motion must close at zero lift after exactly 360 degrees")
    return base, roller, slope, segments


def check_design(data, *, budget=4096):
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 10000:
        raise ValueError("check budget must be an integer from 1 through 10000")
    base, roller, slope, segments = load_design(data)
    results = []
    for i, segment in enumerate(segments):
        r, v, a = segment.polynomials(base, roller)
        r2, v2 = mul(r, r), mul(v, v)
        # K is the signed curvature numerator; S is squared pitch speed.
        k = add(add(r2, scale(v2, 2)), scale(mul(r, a), -1))
        speed2 = add(r2, v2)
        pressure = add(scale(r2, slope * slope), scale(v2, -1))
        # Require a strictly convex pitch curve. Then positive
        # S^3 - roller^2 K^2 means pitch curvature radius exceeds the roller.
        undercut = add(mul(mul(speed2, speed2), speed2), scale(mul(k, k), -roller * roller))
        checks = {"pressure": certify(pressure, strict=False, budget=budget),
                  "convex_pitch": certify(k, budget=budget),
                  "roller_curvature": certify(undercut, budget=budget)}
        for item in checks.values():
            if "u" in item:
                item["angle_deg"] = str(segment.start_deg + segment.span_deg * F(item["u"]))
        results.append({"segment": i, "checks": checks})
    statuses = [check["status"] for row in results for check in row["checks"].values()]
    status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    return {"status": status, "model": "convex in-line radial roller cam; 3-4-5 motion",
            "pressure_angle_limit_deg_approx": math.degrees(math.atan(float(slope))),
            "segments": results}
