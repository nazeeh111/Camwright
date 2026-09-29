"""Calculation and complete in-memory delivery around the reviewed kernel."""
import base64
import copy
import io
import json
import zipfile

from . import __version__, curve_export, geometry
from .project import compact_result, derived, identity, preview, validate_project

CHECK_BUDGET = 2048
EXPORT_BUDGET = 8192
MAX_ZIP_BYTES = 8 * 1024 * 1024


def refused(code, message, status="unknown", **extra):
    return {"error": {"code": code, "message": message}, "status": status, **extra}


def calculate(operation, project, project_id=None, *, check_budget=CHECK_BUDGET,
              export_budget=EXPORT_BUDGET):
    validate_project(project)
    current_id = identity(project)
    if operation == "export" and project_id != current_id:
        return refused("stale_project", "Check the current project before exporting")
    checks = geometry.check_design(project, budget=check_budget)
    if operation == "check":
        return {"project_id": current_id, "result": compact_result(checks, project),
                "derived": derived(project), "preview": preview(project)}
    if operation != "export":
        raise ValueError("unknown calculation operation")
    if checks["status"] != "pass":
        return refused("geometry_refused", "Export requires current geometric Pass", checks["status"],
                       result=compact_result(checks, project))
    export = curve_export.build_export(project, tolerance=project["tolerance_mm"], budget=export_budget)
    report = export["report"]
    if report["status"] != "pass":
        return refused("tolerance_unresolved", "Requested curve tolerance remains unresolved", report=report)
    report = copy.deepcopy(report)
    report.update({"project_id": current_id, "implementation_version": __version__,
                   "model": project["model"], "angle_units": "degrees",
                   "orientation": "+X at zero degrees; counterclockwise; +Y upward; SVG negates Y",
                   "cam_curve": "physical inward roller-normal offset",
                   "pitch_curve": "roller-centre path"})
    files = dict(export["files"])
    files["export.json"] = json.dumps(report, indent=2)+"\n"
    files["checks.json"] = json.dumps(checks, indent=2)+"\n"
    files["camwright-project.json"] = json.dumps(project, indent=2, ensure_ascii=True)+"\n"
    if sum(len(contents.encode()) for contents in files.values()) > 16 * 1024 * 1024:
        return refused("output_limit", "Export exceeds the bounded output size")
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for filename, contents in files.items():
            info = zipfile.ZipInfo(filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, contents)
    raw = memory.getvalue()
    if len(raw) > MAX_ZIP_BYTES:
        return refused("output_limit", "Export exceeds the bounded download size")
    return {"status": "pass", "project_id": current_id,
            "zip_base64": base64.b64encode(raw).decode("ascii"),
            "summary": {key: report[key] for key in ["vertices", "maximum_cam_bound_mm", "maximum_pitch_bound_mm"]}}
