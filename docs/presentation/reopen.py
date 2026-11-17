"""Read-only standard-library inspection of the frozen Camwright worked example."""
from pathlib import Path
import json,hashlib,zipfile
P=Path(__file__).resolve().parent
for name,h in json.loads((P/'MANIFEST.json').read_text()).items():
    if hashlib.sha256((P/name).read_bytes()).hexdigest()!=h:raise ValueError('Changed member: '+name)
with zipfile.ZipFile(P/'failure-inspection.zip') as z:failure=json.loads(z.read('inspection.json'))
with zipfile.ZipFile(P/'profile.zip') as z:geometry=json.loads(z.read('export.json'));project=json.loads(z.read('camwright-project.json'))
grid=json.loads((P/'radius-grid.json').read_text())
print(json.dumps({'failed_inspection':failure['result']['status'],'cam_angle_witness_deg':failure['result']['segments'][0]['checks']['pressure']['angle_deg'],'nine_pair_outcomes':{s:sum(r['status']==s for r in grid['candidates']) for s in ('pass','fail','unknown')},'minimum_within_grid':grid['minimum_within_grid'],'selected_base_mm':project['base_radius'],'selected_roller_mm':project['roller_radius'],'cam_bound_mm':geometry['maximum_cam_bound_mm'],'scope':'Stored geometric evidence only; fresh rechecking requires the complete current Camwright source, not hardware approval'},indent=2))
