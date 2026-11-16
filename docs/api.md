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
| GET `/api/health` | None | Read-only service, implementation version, model, units and local-only identity; no project/path/result |
| GET `/api/example` | None | Bundled default project |
| POST `/api/validate` | `{project}` | `{project, project_id, derived}` after complete validation |
| POST `/api/draft` | `{project}` | `{derived}`; individual bounds apply, cycle closure does not; no geometry/check state |
| POST `/api/check` | `{project}` | `{project_id, inspection_id, result, derived, preview, implementation_version, check_limits}` |
| POST `/api/point` | `{project, angle_deg}` | Visual-only `{angle_deg, lift_mm, cam:[x,y], pitch:[x,y], roller_radius_mm}` |
| POST `/api/export` | `{project, project_id}` | Complete ZIP after fresh current-input checks, or 409 with no geometry |
| POST `/api/inspection` | `{project, project_id, inspection_id}` | Saved completed check ZIP, or 409 for a missing/replaced/mismatched snapshot |
| POST `/api/cancel` | `{project_id}` | `{cancelled}`; kills only the active matching calculation |

`derived` contains exact rational strings `total_deg_exact`, `remaining_deg_exact`, and `segments` with `segment`, `start_deg_exact`, `end_deg_exact`, `start_mm_exact`, `end_mm_exact`, `motion` (`rise`, `return`, `dwell`). A complete project requires 360° and final zero lift. Draft summaries provide negative remaining degrees for an overfilled cycle.

`result.segments[].checks` contains `pressure`, `convex_pitch`, `roller_curvature`: each has `status` and `boxes`; failure includes `u`, `angle_deg`, bounded `value`; unknown includes `interval`, exact `angle_interval_deg`, and reason `work_or_depth_limit`. Pass leaves are omitted from the UI response and retained in ZIP `checks.json`. The pressure angle field is a configured limit approximation, not an observed maximum.

`preview` has `visual_only:true` and `points` containing the point fields above. It retains every join and 33 positions per segment, plus a one-degree grid. It is never evidence for geometric or export Pass.

`inspection_id` is an opaque receipt for the server's one current completed check. `/api/inspection` accepts no result or status fields and performs no calculation. It requires the exact current project identity and receipt. The server freezes the completed check's native compact result, derived spans and exact project strings, excluding sampled preview geometry. A new check request invalidates the prior receipt, including a check rejected for invalid project inputs. An active check that is superseded cannot restore its old snapshot. Failed, cancelled or timed-out checks and server shutdown leave no savable inspection. Profile export recomputes independently and does not replace a completed inspection. A snapshot is shared by tabs connected to the same local server; another tab's check can replace it.

The inspection ZIP contains only `inspection.json` and `inspection.html`. The JSON has `schema:"camwright.inspection"`, `version:1`, project/receipt identities, UTC completion time, implementation version, model/units, actual `check_limits`, worker deadline, exact `project`, `derived`, and native `result`. Current checks use 2,048 interval evaluations per condition and segment and maximum subdivision depth 24. Snapshot memory, combined uncompressed archive contents and download size are each limited to 512 KiB. Native Pass, Fail and Unknown (`unknown`, displayed as Unresolved) are all savable; this is a saved observation, not hardware approval or an export-tolerance Pass. The literal-escaped readonly HTML uses no scripts, remote assets or network requests. The report includes keyboard-focusable scrolling tables for narrow screens. It does not import saved statuses into the workspace. To reuse inputs, extract the JSON's project object into a project file and open it normally, then run a fresh check.

Geometry ZIP headers include `X-Camwright-Project-Id`, `X-Camwright-Vertices`, `X-Camwright-Cam-Bound-Mm`, `X-Camwright-Pitch-Bound-Mm`. Inspection ZIP headers include project identity and `X-Camwright-Inspection-Id`. Full geometry interval certificates and version/orientation/project identity are in `export.json`. HTTP 400 rejects invalid projects/receipts; 403 rejects Host/Origin; 413 rejects body length; 415 rejects content type; 429 indicates a busy worker; 409 reports export refusal, missing/stale inspection, timeout or cancellation. Fixed static assets are `/`, `/index.html`, `/app.js`, `/styles.css`, `/favicon.svg`. Requests never select filesystem paths.

## Finite radius exploration and selection

`POST /api/explore` takes `{project,options}`. Options have exactly
`base_radii`, `roller_radii` (lists of1–16 distinct positive exact fixed-decimal
strings), and `max_candidates` (integer1–64). The Cartesian product is at most64.
Only those two dimensions change; motion, pressure constraint, units and export
tolerance stay tied to the source project. One existing worker slot and30-second
hard deadline applies. `/api/cancel` uses the original source project identity.
No failed/cancelled/deadline worker creates geometry.

Every evaluated cell has its original indices, exact radii/project identity and
native `pass`, `fail` or `unknown` checks. Evaluation order is zero-lift pitch
radius `base+roller`, then base, roller and original indices. This is a declared
geometric packaging criterion, not a physical load/wear proxy or an assumption
that changing radii is monotonic. The result has a source-bound `request`, its
`request_id`, evaluated/total counts, candidate budget, `complete`, `status`
(`complete`/`unfinished`), and a best checked `selection` when available. The
`outcome` distinguishes a passing candidate, unknown space and a completely
classified all-fail grid. Only a complete grid with no unknowns can set
`minimum_within_grid:true`. Any unknown or unfinished work conservatively prevents
that claim, even if a later candidate passes. There is no minimum claim outside
the declared grid. A direct library cancellation callback is cooperative between
bounded candidate checks; the server's process cancellation remains immediate.

`POST /api/select` takes `{project,project_id,options}`. Its options have exactly
`base_radii`, `roller_radii`, `request_id`, `base_index`, `roller_index`.
The current source and grid must match their identity. The chosen candidate is
then freshly checked; saved classifications, best flags or mesh data are never
authority. Failure/unknown produces `selection_refused`, with no chosen project
or geometry. Success returns the exact chosen `project`, its new `project_id`,
the source/grid identities and `selection_rechecked:true`. Run the existing
check/export workflow on that project. These operations do not replace the
server's saved inspection receipt; a new selected-project check does.

## CAD exchange

A successful geometry ZIP normally also contains `cam.dxf` and `pitch.dxf`.
Each is an ASCII R2000 closed LWPOLYLINE in the+Z plane, `$INSUNITS=4` (mm), with no
bulges. Its vertices are exactly the existing certified12-place CSV decimals,
without the repeated final closure vertex. The CLOSED flag supplies the same
final certified chord. No coordinate recomputation, Y inversion, spline fitting
or cutter compensation is introduced. Export metadata records format status;
`X-Camwright-CAD-Status` is `pass` or `unavailable`.

A mathematically admitted tiny cam/coarse tolerance can yield too few distinct
emitted vertices for a nondegenerate CAD face. Its certified CSV/SVG remain
available, while metadata explicitly marks DXF unavailable and omits both DXFs.
Request a tighter tolerance if possible; finer exports can still hit the existing
work budget. This preserves the supported mathematical exporter without
fabricating a CAD contour. Valid native CAD entities are not fabrication or
hardware approval.

CLI inputs must be regular files and are captured once through a nonblocking, byte-bounded descriptor. FIFOs and devices are refused. Output publication never overwrites an existing path. If complete publication succeeds but removal of its owned staging file fails, the command succeeds and writes a structured cleanup warning to stderr identifying the leftover staging path. It does not retry a permission failure.
