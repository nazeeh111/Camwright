"""Versioned projects, exact input preservation, and visual-only previews."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math

from . import geometry

MAX_BODY = 32768
PROJECT_KEYS = {"schema", "version", "units", "angle_units", "model", "base_radius",
                "roller_radius", "maximum_pressure_slope", "tolerance_mm", "segments"}
MODEL = "inline-roller-345-convex"


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} requires exactly: {', '.join(sorted(keys))}")


def parse_json(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BODY:
        raise ValueError("JSON exceeds 32 KiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_number(value):
        raise ValueError("project numbers must be fixed-decimal strings")

    def small_integer(value):
        if len(value) > 6:
            raise ValueError("JSON integer is too long")
        return int(value)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_float=reject_number, parse_constant=reject_number,
                          parse_int=small_integer)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("invalid or excessively nested JSON") from error


def validate_project(project, *, require_closed=True):
    exact_keys(project, PROJECT_KEYS, "project")
    if (project["schema"] != "camwright.project" or type(project["version"]) is not int or
            project["version"] != 1 or project["units"] != "mm" or
            project["angle_units"] != "degrees" or project["model"] != MODEL):
        raise ValueError("unsupported project schema, version, units or model")
    for key in ["base_radius", "roller_radius", "maximum_pressure_slope", "tolerance_mm"]:
        if not isinstance(project[key], str):
            raise ValueError(f"{key} must be an exact fixed-decimal string")
    tolerance = geometry.rational(project["tolerance_mm"], "tolerance_mm")
    if not Fraction(1, 10000) <= tolerance <= 1:
        raise ValueError("tolerance_mm must be from 0.0001 through 1 mm")
    rows = project["segments"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
        raise ValueError("one to twelve segments are required")
    for row in rows:
        exact_keys(row, {"span_deg", "end_mm"}, "segment")
        if not all(isinstance(row[key], str) for key in row):
            raise ValueError("segment dimensions must be exact fixed-decimal strings")
    if require_closed:
        geometry.load_design(project)
    else:
        base, roller, slope = [geometry.rational(project[key], key) for key in
                               ["base_radius", "roller_radius", "maximum_pressure_slope"]]
        if base <= 0 or roller <= 0 or not 0 < slope <= 1:
            raise ValueError("positive radii and a pressure slope in (0,1] are required")
        for row in rows:
            if geometry.rational(row["span_deg"], "span_deg") <= 0 or geometry.rational(row["end_mm"], "end_mm") < 0:
                raise ValueError("segment angles must be positive and lift nonnegative")
    return project


def identity(project):
    return hashlib.sha256(json.dumps(project, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=True).encode()).hexdigest()


def derived(project, *, require_closed=True):
    if require_closed:
        _, _, _, segments = geometry.load_design(project)
    else:
        segments = []
        start, height = Fraction(0), Fraction(0)
        for row in project["segments"]:
            span = geometry.rational(row["span_deg"], "span_deg")
            end = geometry.rational(row["end_mm"], "end_mm")
            segments.append(geometry.Segment(start, span, height, end))
            start, height = start+span, end
    total = segments[-1].start_deg+segments[-1].span_deg
    return {"total_deg_exact": str(total), "remaining_deg_exact": str(360-total), "segments": [
        {"segment": index, "start_deg_exact": str(segment.start_deg),
         "end_deg_exact": str(segment.start_deg + segment.span_deg),
         "start_mm_exact": str(segment.start_mm), "end_mm_exact": str(segment.end_mm),
         "motion": "rise" if segment.end_mm > segment.start_mm else
                   "return" if segment.end_mm < segment.start_mm else "dwell"}
        for index, segment in enumerate(segments)]}


def _point(angle, base, roller, segments):
    normalized = angle % 360
    segment = next(s for s in segments if s.start_deg <= normalized < s.start_deg+s.span_deg)
    u = float((normalized-segment.start_deg)/segment.span_deg)
    height = float(segment.start_mm) + float(segment.end_mm-segment.start_mm)*(10*u**3-15*u**4+6*u**5)
    velocity = float(segment.end_mm-segment.start_mm)*(30*u**2-60*u**3+30*u**4)/math.radians(float(segment.span_deg))
    radius = float(base+roller)+height
    theta = math.radians(float(normalized))
    cosine, sine = math.cos(theta), math.sin(theta)
    pitch = [radius*cosine, radius*sine]
    length = math.hypot(radius, velocity)
    normal = [(radius*cosine+velocity*sine)/length, (radius*sine-velocity*cosine)/length]
    return {"angle_deg": float(angle), "lift_mm": height,
            "cam": [p-float(roller)*n for p, n in zip(pitch, normal)], "pitch": pitch,
            "roller_radius_mm": float(roller)}


def point(project, angle_text):
    if not isinstance(angle_text, str):
        raise ValueError("angle_deg must be a fixed-decimal string")
    angle = geometry.rational(angle_text, "angle_deg")
    if not 0 <= angle <= 360:
        raise ValueError("angle_deg must be from 0 through 360")
    base, roller, _, segments = geometry.load_design(project)
    return _point(angle, base, roller, segments)


def preview(project):
    base, roller, _, segments = geometry.load_design(project)
    angles = {Fraction(angle) for angle in range(361)}
    for segment in segments:
        angles.update(segment.start_deg+segment.span_deg*Fraction(i, 32) for i in range(33))
    return {"visual_only": True, "points": [_point(angle, base, roller, segments) for angle in sorted(angles)]}


def compact_result(result, project):
    """Keep UI responses small; complete proof leaves remain in exported checks."""
    _, _, _, segments = geometry.load_design(project)
    for row, segment in zip(result["segments"], segments):
        for check in row["checks"].values():
            check.pop("leaves", None)
            if "interval" in check:
                check["angle_interval_deg"] = [str(segment.start_deg+segment.span_deg*Fraction(u))
                                                for u in check["interval"]]
                check["reason"] = "work_or_depth_limit"
    return result
