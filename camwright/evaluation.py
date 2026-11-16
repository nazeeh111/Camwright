"""Calculation and complete in-memory delivery around the reviewed kernel."""
import base64
import copy
import io
import json
import zipfile

from . import __version__, curve_export, geometry
from .project import compact_result, derived, identity, preview, validate_project, parse_json

CHECK_BUDGET = 2048
EXPORT_BUDGET = 8192
MAX_ZIP_BYTES = 8 * 1024 * 1024


def refused(code, message, status="unknown", **extra):
    return {"error": {"code": code, "message": message}, "status": status, **extra}


def snapshot_project(project):
    """Detach exact inputs before identity, checks or any output authority."""
    snapshot = parse_json(json.dumps(project, ensure_ascii=True, allow_nan=False).encode())
    validate_project(snapshot)
    return snapshot


def evaluate(project, *, check_budget=CHECK_BUDGET):
    snapshot = snapshot_project(project)
    return {"project": snapshot, "project_id": identity(snapshot),
            "checks": geometry.check_design(snapshot, budget=check_budget)}


def calculate(operation, project, project_id=None, *, check_budget=CHECK_BUDGET,
              export_budget=EXPORT_BUDGET, options=None):
    if operation in {"explore", "select"}:
        from .sizing import explore, select
        if operation == "explore":
            return explore(project, options, check_budget=check_budget)
        return select(project, options, project_id=project_id, check_budget=check_budget)
    project = snapshot_project(project)
    current_id = identity(project)
    if operation == "export" and project_id != current_id:
        return refused("stale_project", "Check the current project before exporting")
    evaluation = evaluate(project, check_budget=check_budget)
    project, current_id, checks = evaluation["project"], evaluation["project_id"], evaluation["checks"]
    if operation == "check":
        return {"project_id": current_id, "result": compact_result(checks, project),
                "derived": derived(project), "preview": preview(project),
                "implementation_version": __version__,
                "check_limits": {"interval_budget_per_condition": check_budget,
                                 "maximum_subdivision_depth": 24}}
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
    from .dxf import from_csv, UnrepresentablePolyline
    try:
        dxf_files={name+".dxf":from_csv(files[name+".csv"], layer=name.upper()) for name in ("cam","pitch")}
    except UnrepresentablePolyline as error:
        report["dxf"]={"status":"unavailable","reason":str(error),"action":"Request a tighter curve tolerance; certified CSV/SVG remain available."}
    else:
        files.update(dxf_files)
        report["dxf"] = {"status":"pass", "entity": "closed LWPOLYLINE", "units": "mm", "insunits": 4,
                     "plane": "+Z", "coordinates": "same 12-place CSV decimals; no bulges",
                     "closure": "duplicate final CSV vertex omitted; CLOSED flag supplies last chord"}
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
            "summary": {**{key: report[key] for key in ["vertices", "maximum_cam_bound_mm", "maximum_pitch_bound_mm"]}, "cad_status": report["dxf"]["status"]}}
