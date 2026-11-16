"""Finite geometric radius exploration; no monotonic or physical-cost assumption."""
import copy
from fractions import Fraction
import hashlib
import json
from . import geometry
from .project import validate_project, identity, exact_keys, compact_result


def request(project, options):
    validate_project(project)
    from .project import parse_json
    options=parse_json(json.dumps(options,ensure_ascii=True,allow_nan=False).encode())
    exact_keys(options,{'base_radii','roller_radii','max_candidates'},'sizing options')
    limit=options['max_candidates']
    if type(limit) is not int or not 1<=limit<=64:raise ValueError('max_candidates must be1through64')
    arrays=[]
    for name in ('base_radii','roller_radii'):
        raw=options[name]
        if type(raw) is not list or not 1<=len(raw)<=16 or any(type(value) is not str for value in raw):
            raise ValueError('Each radius list needs1through16 exact fixed-decimal strings')
        values=[geometry.rational(value,name) for value in raw]
        if any(value<=0 for value in values) or len(set(values))!=len(values):
            raise ValueError('Radius values must be positive and numerically distinct')
        arrays.append(list(raw))
    if len(arrays[0])*len(arrays[1])>64:raise ValueError('Sizing grid exceeds64 candidates')
    payload={'schema':'camwright.sizing','version':1,'source_project_id':identity(project),
             'project':copy.deepcopy(project),'base_radii':arrays[0],'roller_radii':arrays[1],
             'objective':'minimum_zero_lift_pitch_radius_then_base_then_roller'}
    payload['request_id']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return payload,limit


def explore(project, options, *, check_budget=2048, cancel=None):
    from .evaluation import evaluate
    # Parse once into a detached snapshot, shared by every candidate.
    if cancel is not None and not callable(cancel):raise ValueError('cancel must be a callable or None')
    if type(check_budget) is not int or not 1<=check_budget<=10000:raise ValueError('check_budget must be1through10000')
    source=evaluate_snapshot(project)
    req,limit=request(source,options)
    candidates=[]
    for i,base in enumerate(req['base_radii']):
        for j,roller in enumerate(req['roller_radii']):
            candidates.append((Fraction(base)+Fraction(roller),Fraction(base),Fraction(roller),i,j))
    candidates.sort()
    rows=[];best=None;reason=None
    for score,_,_,i,j in candidates:
        if cancel is not None and cancel():reason='cancelled';break
        if len(rows)>=limit:reason='candidate_budget';break
        candidate=copy.deepcopy(source);candidate.update(base_radius=req['base_radii'][i],roller_radius=req['roller_radii'][j])
        evaluated=evaluate(candidate,check_budget=check_budget)
        checks=evaluated['checks']
        row={'base_index':i,'roller_index':j,'base_radius':candidate['base_radius'],
             'roller_radius':candidate['roller_radius'],'zero_lift_pitch_radius_mm_exact':str(score),
             'project_id':evaluated['project_id'],'status':checks['status'],
             'result':compact_result(checks,candidate)}
        rows.append(row)
        if row['status']=='pass' and best is None:best={'base_index':i,'roller_index':j,'project_id':row['project_id']}
    complete=len(rows)==len(candidates)
    statuses=[row['status'] for row in rows]
    return {'schema':'camwright.sizing-result','version':1,'request':req,'complete':complete,
            'status':'complete' if complete else 'unfinished','reason':reason,
            'outcome':'passing_candidate' if best else 'unknown' if not complete or 'unknown' in statuses else 'no_pass_in_grid',
            'minimum_within_grid':bool(best and complete and 'unknown' not in statuses),
            'selection':best,'candidates':rows,'evaluated':len(rows),'total':len(candidates),
            'candidate_budget':limit,'check_limits':{'interval_budget_per_condition':check_budget,'maximum_subdivision_depth':24},
            'scope':'Declared finite radii only; geometric model, not loads, wear or manufacturing approval.'}


def evaluate_snapshot(project):
    from .evaluation import snapshot_project
    return snapshot_project(project)


def select(project, options, *, project_id, check_budget=2048):
    from .evaluation import evaluate,refused
    source=evaluate_snapshot(project)
    exact_keys(options,{'base_radii','roller_radii','request_id','base_index','roller_index'},'selection options')
    req,_=request(source,{'base_radii':options['base_radii'],'roller_radii':options['roller_radii'],'max_candidates':64})
    if project_id!=identity(source) or req['request_id']!=options['request_id']:
        return refused('stale_sizing','Selection differs from its current source or finite grid')
    i,j=options['base_index'],options['roller_index']
    if type(i) is not int or type(j) is not int or not 0<=i<len(req['base_radii']) or not 0<=j<len(req['roller_radii']):
        raise ValueError('Invalid finite candidate indices')
    candidate=copy.deepcopy(source);candidate.update(base_radius=req['base_radii'][i],roller_radius=req['roller_radii'][j])
    result=evaluate(candidate,check_budget=check_budget)
    if result['checks']['status']!='pass':
        return refused('selection_refused','Selection requires a fresh geometric Pass',result['checks']['status'],result=compact_result(result['checks'],candidate))
    return {'status':'pass','project':candidate,'project_id':result['project_id'],
            'source_project_id':identity(source),'request_id':req['request_id'],
            'result':compact_result(result['checks'],candidate),'selection_rechecked':True}
