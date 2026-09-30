"""Small readonly records of completed checks, with no geometry or execution."""
import base64
from html import escape
import io
import json
import zipfile

MAX_INSPECTION_BYTES = 512 * 1024
STATES = {"pass": "Pass", "fail": "Fail", "unknown": "Unresolved"}
LABELS = {"pressure": "Pressure limit", "convex_pitch": "Strictly convex pitch",
          "roller_curvature": "Local roller curvature"}


def render_html(document):
    """Escape literal text even though native project inputs are restricted."""
    def text(value):
        return escape(str(value), quote=True)

    def table(caption, headings, rows):
        return ('<div class="table-scroll" tabindex="0" role="region" aria-label="' +
                text(caption) + '"><table><caption>' + text(caption) + '</caption><thead><tr>' +
                ''.join('<th scope="col">' + text(h) + '</th>' for h in headings) +
                '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + text(c) + '</td>'
                for c in row) + '</tr>' for row in rows) + '</tbody></table></div>')

    project, result = document["project"], document["result"]
    metadata = [("Completed (UTC)", document["completed_at_utc"]),
                ("Implementation version", document["implementation_version"]),
                ("Inspection schema", f'{document["schema"]} v{document["version"]}'),
                ("Inspection receipt", document["inspection_id"]),
                ("Project identity (SHA-256)", document["project_id"]),
                ("Model", document["model"]), ("Units", document["units"]),
                ("Angle units", document["angle_units"]),
                ("Interval budget per condition / segment", document["check_limits"]["interval_budget_per_condition"]),
                ("Maximum subdivision depth", document["check_limits"]["maximum_subdivision_depth"]),
                ("Worker deadline (seconds)", document["worker_deadline_seconds"])]
    inputs = [(label, project[key]) for key, label in [
        ("base_radius", "Base radius (mm)"), ("roller_radius", "Roller radius (mm)"),
        ("maximum_pressure_slope", "Maximum pressure slope"), ("tolerance_mm", "Requested export deviation (mm)")]]
    motion = [(i+1, row["span_deg"], row["end_mm"], summary["start_deg_exact"],
               summary["end_deg_exact"], summary["motion"]) for i, (row, summary) in
              enumerate(zip(project["segments"], document["derived"]["segments"]))]
    conditions = []
    for row in result["segments"]:
        for key, check in row["checks"].items():
            evidence = []
            for field, label in [("u", "Witness parameter u"), ("angle_deg", "Witness angle (degrees)"),
                                 ("value", "Bounded condition value"), ("interval", "Parameter interval"),
                                 ("angle_interval_deg", "Angle interval (degrees)"), ("reason", "Reason")]:
                if field in check:
                    value = check[field]
                    evidence.append(label + ': ' + (' to '.join(value) if isinstance(value, list) else str(value)))
            conditions.append((row["segment"]+1, LABELS.get(key, key), STATES.get(check["status"], check["status"]),
                               check["boxes"], '; '.join(evidence) or 'Continuous interval check completed'))
    body = (table("Recorded implementation and limits", ["Field", "Value"], metadata) +
            table("Exact entered dimensions", ["Field", "Entered string"], inputs) +
            table("Motion cycle", ["Segment", "Entered span (degrees)", "Entered end lift (mm)",
                                   "Exact start (degrees)", "Exact end (degrees)", "Motion"], motion) +
            table("Native geometric conditions", ["Segment", "Condition", "Status", "Intervals examined", "Evidence"], conditions))
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>Camwright saved inspection</title>
<style>body{font:16px/1.5 system-ui,sans-serif;color:#172c35;background:#f6f8f7;margin:0;padding:clamp(12px,3vw,32px)}main{max-width:1100px;margin:auto}h1{font-size:1.6rem}p{max-width:78ch}strong{font-weight:700}.table-scroll{overflow:auto;margin:24px 0;background:white;border:1px solid #ced9d5;border-radius:6px}.table-scroll:focus{outline:3px solid #246659;outline-offset:2px}table{border-collapse:collapse;width:100%;font-size:.9rem}caption{text-align:left;padding:12px;font-weight:700}th,td{text-align:left;vertical-align:top;padding:10px;border-top:1px solid #dee6e2;overflow-wrap:anywhere}th{background:#edf3f0}td:last-child{min-width:140px}th:first-child{min-width:70px}code{overflow-wrap:anywhere}@media(max-width:480px){body{padding:12px}th,td{padding:8px}table{font-size:.85rem}}</style></head><body><main>
<h1>Camwright saved inspection</h1>
<p><strong>Saved observation · ''' + text(STATES.get(result["status"], result["status"])) + '''</strong></p>
<p>This records the completed native geometric check under the recorded model and limits. It is not a current workspace result or hardware approval. No geometry export or export-tolerance Pass is established by this inspection.</p>
<p>Pass means the condition was established under the geometric model. Fail includes a witness. Unresolved means the work or depth limit could not establish a result; it never means Pass. Exact fractions are preserved below. The requested export deviation is an input, not an achieved bound.</p>
<p>This readonly report works offline. Use Tab to focus a table and arrow keys to scroll on a narrow screen. The adjacent inspection.json contains the exact entered project strings and the native result. To reuse inputs, save its project object as a project JSON and open it in Camwright, then check again.</p>
''' + body + '\n</main></body></html>\n'


def build_archive(snapshot):
    """Consume only frozen backend bytes; bound both decoded and ZIP output."""
    if len(snapshot) > MAX_INSPECTION_BYTES:
        raise ValueError("Inspection exceeds the bounded record size")
    document = json.loads(snapshot)
    files = {"inspection.json": json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False)+'\n',
             "inspection.html": render_html(document)}
    if sum(len(contents.encode("utf-8")) for contents in files.values()) > MAX_INSPECTION_BYTES:
        raise ValueError("Inspection exceeds the bounded output size")
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for filename, contents in files.items():
            info = zipfile.ZipInfo(filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, contents)
    raw = memory.getvalue()
    if len(raw) > MAX_INSPECTION_BYTES:
        raise ValueError("Inspection exceeds the bounded download size")
    return {"project_id": document["project_id"], "inspection_id": document["inspection_id"],
            "zip_base64": base64.b64encode(raw).decode("ascii")}
