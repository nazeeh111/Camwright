# Local API

All POSTs require the printed `Host`, matching `Origin`, `Content-Type: application/json`, one bounded `Content-Length`, no transfer encoding, and a UTF-8 JSON body at most 32 KiB. Duplicate keys, unexpected fields and unsupported numeric notation are rejected. Errors are `{ "error": { "code": "...", "message": "..." } }`, with calculation `status` where applicable. Status strings are `pass`, `fail`, `unknown`.

Project shape:

```json
{
  "schema": "camwright.project", "version": 1,
  "units": "mm", "angle_units": "degrees", "model": "inline-roller-345-convex",
  "base_radius": "25", "roller_radius": "5", "maximum_pressure_slope": "0.5",
  "tolerance_mm": "0.01",
  "segments": [{"span_deg": "120", "end_mm": "20"}, {"span_deg": "60", "end_mm": "20"},
               {"span_deg": "120", "end_mm": "0"}, {"span_deg": "60", "end_mm": "0"}]
}
```

Numeric values in projects are exact fixed-decimal strings; `version` is the only integer. Bounds and model conventions are in the README. Project identity is SHA-256 of sorted, compact JSON, preserving the entered strings.

| Route | Request | Result |
| --- | --- | --- |
| GET `/api/example` | None | Bundled default project |
| POST `/api/validate` | `{project}` | `{project, project_id, derived}` after complete validation |
| POST `/api/draft` | `{project}` | `{derived}`; individual bounds apply, cycle closure does not; no geometry/check state |
| POST `/api/check` | `{project}` | `{project_id, result, derived, preview}` |
| POST `/api/point` | `{project, angle_deg}` | Visual-only `{angle_deg, lift_mm, cam:[x,y], pitch:[x,y], roller_radius_mm}` |
| POST `/api/export` | `{project, project_id}` | Complete ZIP after fresh current-input checks, or 409 with no geometry |
| POST `/api/cancel` | `{project_id}` | `{cancelled}`; kills only the active matching calculation |

`derived` contains exact rational strings `total_deg_exact`, `remaining_deg_exact`, and `segments` with `segment`, `start_deg_exact`, `end_deg_exact`, `start_mm_exact`, `end_mm_exact`, `motion` (`rise`, `return`, `dwell`). A complete project requires 360° and final zero lift. Draft summaries provide negative remaining degrees for an overfilled cycle.

`result.segments[].checks` contains `pressure`, `convex_pitch`, `roller_curvature`: each has `status` and `boxes`; failure includes `u`, `angle_deg`, bounded `value`; unknown includes `interval`, exact `angle_interval_deg`, and reason `work_or_depth_limit`. Pass leaves are omitted from the UI response and retained in ZIP `checks.json`. The pressure angle field is a configured limit approximation, not an observed maximum.

`preview` has `visual_only:true` and `points` containing the point fields above. It retains every join and 33 positions per segment, plus a one-degree grid. It is never evidence for geometric or export Pass.

ZIP headers include `X-Camwright-Project-Id`, `X-Camwright-Vertices`, `X-Camwright-Cam-Bound-Mm`, `X-Camwright-Pitch-Bound-Mm`. Full interval certificates and version/orientation/project identity are in `export.json`. HTTP 400 rejects invalid projects; 403 rejects Host/Origin; 413 rejects body length; 415 rejects content type; 429 indicates a busy worker; 409 reports export refusal, timeout or cancellation. Fixed static assets are `/`, `/index.html`, `/app.js`, `/styles.css`, `/favicon.svg`. Requests never select filesystem paths.
