"""Conservative adaptive polylines, including serialized-coordinate error.

Each accepted chord stays within the requested distance of its original curve
over the whole parameter interval. No chord crosses a motion-program join.
"""
from fractions import Fraction as F
import io
import csv
import json
import math

from . import geometry as cam


def absolute(value):
    return max(abs(value.lo), abs(value.hi))


def squared(value):
    low = 0 if value.lo <= 0 <= value.hi else min(value.lo**2, value.hi**2)
    return cam.I(F(low), max(value.lo**2, value.hi**2))


def sqrt_interval(value, digits=32):
    if value.lo < 0:
        raise ValueError("square-root interval is negative")
    denominator = 10**digits

    def floor_root(v):
        return math.isqrt(v.numerator * denominator**2 // v.denominator)

    lo = floor_root(value.lo)
    hi = floor_root(value.hi)
    if hi**2 * value.hi.denominator != value.hi.numerator * denominator**2:
        hi += 1
    return cam.I(F(lo, denominator), F(hi, denominator))


def trigonometry(degrees):
    # Exact degree reduction keeps the Taylor argument in [-pi/4,pi/4].
    quadrant = math.floor((degrees + 45) / 90)
    reduced = degrees - quadrant * 90
    angle = cam.PI * (reduced / 180)
    sin_coefficients = [cam.I.exact(0) for _ in range(25)]
    cos_coefficients = [cam.I.exact(0) for _ in range(25)]
    for degree in range(25):
        if degree % 2:
            sin_coefficients[degree] = cam.I.exact(F((-1)**((degree-1)//2), math.factorial(degree)))
        else:
            cos_coefficients[degree] = cam.I.exact(F((-1)**(degree//2), math.factorial(degree)))
    remainder = absolute(angle)**25 / math.factorial(25)
    uncertainty = cam.I(-remainder, remainder)
    sine = cam.evaluate(sin_coefficients, angle) + uncertainty
    cosine = cam.evaluate(cos_coefficients, angle) + uncertainty
    rotation = quadrant % 4
    return [(cosine, sine), (-sine, cosine), (-cosine, -sine), (sine, -cosine)][rotation]


def serialized(value, digits=12):
    denominator = 10**digits
    integer = round((value.lo + value.hi) * denominator / 2)
    emitted = F(integer, denominator)
    sign = "-" if integer < 0 else ""
    whole, fraction = divmod(abs(integer), denominator)
    text = f"{sign}{whole}.{fraction:0{digits}d}"
    error = max(abs(emitted-value.lo), abs(emitted-value.hi))
    return text, emitted, error


def upper_decimal(value, digits=24):
    """Outward rounding keeps certificate numbers small and still conservative."""
    denominator = 10**digits
    rational = F(math.ceil(value*denominator), denominator)
    return serialized(cam.I.exact(rational), digits)[0], rational


def range_of(bernstein):
    return cam.I(min(c.lo for c in bernstein), max(c.hi for c in bernstein))


def second_derivative_bounds(polynomials, roller):
    radius, velocity, acceleration, jerk = map(range_of, polynomials)
    if radius.lo <= 0:
        return None
    speed2 = squared(radius) + squared(velocity)
    k = squared(radius) + 2*squared(velocity) - radius*acceleration
    kprime = 2*radius*velocity + 3*velocity*acceleration - radius*jerk
    sprime = 2*velocity*(radius+acceleration)
    phi_prime = k / speed2
    phi_second = (kprime*speed2-k*sprime) / squared(speed2)
    pitch_bound = absolute(acceleration-radius) + 2*absolute(velocity)
    cam_bound = pitch_bound + roller*(absolute(phi_second)+absolute(phi_prime)**2)
    return cam_bound, pitch_bound


def endpoint(segment, angle, base, roller):
    u = (angle-segment.start_deg)/segment.span_deg
    radius, velocity, _ = segment.polynomials(base, roller)
    r, v = cam.evaluate(radius, u), cam.evaluate(velocity, u)
    cosine, sine = trigonometry(angle)
    px, py = r*cosine, r*sine
    length = sqrt_interval(squared(r)+squared(v))
    nx, ny = (r*cosine+v*sine)/length, (r*sine-v*cosine)/length
    pairs = {"cam": (px-roller*nx, py-roller*ny), "pitch": (px, py)}
    output = {}
    for name, (x, y) in pairs.items():
        sx, ex, dx = serialized(x)
        sy, ey, dy = serialized(y)
        output[name] = {"x": sx, "y": sy, "emitted_x": ex, "emitted_y": ey, "error": dx+dy}
    return output


def build_export(data, *, tolerance="0.01", budget=16384, max_depth=24):
    tolerance_input = str(tolerance)
    tolerance = cam.rational(tolerance, "tolerance")
    if not F(1, 10**6) <= tolerance <= 1:
        raise ValueError("tolerance must be between 0.000001 and 1 millimetre")
    for label, value, maximum in [("export budget", budget, 50000), ("export depth", max_depth, 30)]:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(f"{label} must be an integer from 1 through {maximum}")
    base, roller, _, segments = cam.load_design(data)
    points = []
    certificates = []
    work = 0
    point_cache = {}

    def point_at(angle):
        if angle not in point_cache:
            canonical_angle = angle % 360
            canonical_segment = next(s for s in segments
                                     if s.start_deg <= canonical_angle < s.start_deg+s.span_deg)
            point_cache[angle] = endpoint(canonical_segment, canonical_angle, base, roller)
        return point_cache[angle]

    for index, segment in enumerate(segments):
        radius, velocity, acceleration = segment.polynomials(base, roller)
        jerk = cam.scale(cam.derivative(acceleration), cam.DEGREES_PER_RADIAN / segment.span_deg)
        polynomials = list(map(cam.bernstein, [radius, velocity, acceleration, jerk]))
        stack = [(polynomials, F(0), F(1), 0)]
        while stack:
            if work >= budget:
                return {"report": {"status": "unknown", "reason": "work_budget", "intervals_evaluated": work}, "files": {}}
            polynomials, lo, hi, depth = stack.pop()
            work += 1
            start = segment.start_deg + segment.span_deg*lo
            end = segment.start_deg + segment.span_deg*hi
            left = point_at(start)
            right = point_at(end)
            derivatives = second_derivative_bounds(polynomials, roller)
            delta_text, delta = upper_decimal((end-start)*cam.PI.hi/180)
            bounds = {}
            numbers = {}
            if derivatives is not None:
                for name, derivative in zip(["cam", "pitch"], derivatives):
                    derivative_text, derivative = upper_decimal(derivative, 18)
                    endpoint_text, endpoint_error = upper_decimal(max(left[name]["error"], right[name]["error"]))
                    bound_text, bound = upper_decimal(derivative*delta**2/8+endpoint_error)
                    bounds[name] = bound
                    numbers[name] = {"derivative": derivative_text, "endpoint_error": endpoint_text, "bound": bound_text}
            if bounds and max(bounds.values()) <= tolerance:
                if not points:
                    points.append((start, left))
                points.append((end, right))
                certificates.append({"segment": index, "start_deg_exact": str(start), "end_deg_exact": str(end),
                                     "angular_width_rad_upper": delta_text,
                                     "cam_bound_mm": numbers["cam"]["bound"], "pitch_bound_mm": numbers["pitch"]["bound"],
                                     "cam_second_derivative_bound": numbers["cam"]["derivative"],
                                     "pitch_second_derivative_bound": numbers["pitch"]["derivative"],
                                     "cam_endpoint_error_mm": numbers["cam"]["endpoint_error"],
                                     "pitch_endpoint_error_mm": numbers["pitch"]["endpoint_error"]})
                continue
            if depth >= max_depth:
                return {"report": {"status": "unknown", "reason": "depth_budget", "intervals_evaluated": work,
                                   "start_deg_exact": str(start), "end_deg_exact": str(end)}, "files": {}}
            splits = [cam.split(b) for b in polynomials]
            mid = (lo+hi)/2
            stack.extend([([s[1] for s in splits], mid, hi, depth+1),
                          ([s[0] for s in splits], lo, mid, depth+1)])
    report = {"status": "pass", "units": "mm", "geometric_tolerance_mm": tolerance_input,
              "bound": "maximum Euclidean deviation between continuous curve and serialized polyline",
              "method": "whole-interval second derivative bound times angular width squared / 8, plus endpoint error",
              "vertices": len(points), "intervals_evaluated": work, "coordinate_decimal_places": 12,
              "maximum_cam_bound_mm": upper_decimal(max(F(c["cam_bound_mm"]) for c in certificates))[0],
              "maximum_pitch_bound_mm": upper_decimal(max(F(c["pitch_bound_mm"]) for c in certificates))[0],
              "intervals": certificates,
              "limits": "Geometric approximation only; no dynamic, stress, cutter, or manufacturing approval."}
    extent = math.ceil(max(abs(p[name][key]) for _, p in points for name in ["cam", "pitch"]
                           for key in ["emitted_x", "emitted_y"]))+5
    files = {}
    for name in ["cam", "pitch"]:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["angle_deg_exact", "x_mm", "y_mm"])
        for angle, p in points:
            writer.writerow([str(angle), p[name]["x"], p[name]["y"]])
        files[f"{name}.csv"] = stream.getvalue()
        svg_points = " ".join(f"{p[name]['x']},{serialized(cam.I.exact(-p[name]['emitted_y']))[0]}" for _, p in points)
        files[f"{name}.svg"] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{2*extent}mm" height="{2*extent}mm" '
            f'viewBox="{-extent} {-extent} {2*extent} {2*extent}">'
            f'<title>{name.capitalize()} polyline; tolerance {float(tolerance):g} mm</title>'
            f'<polyline points="{svg_points}" fill="none" stroke="#183d38" stroke-width="0.3"/></svg>\n')
    files["export.json"] = json.dumps(report, indent=2)+"\n"
    return {"report": report, "files": files}
