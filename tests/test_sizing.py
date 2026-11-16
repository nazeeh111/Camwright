import copy,json,unittest
from fractions import Fraction as F
from pathlib import Path
from camwright.sizing import explore,select
from camwright.project import identity


def example():return json.loads((Path(__file__).parents[1]/'camwright/examples/accepted.json').read_text())

def circle():
    p=example();p['segments']=[{'span_deg':'360','end_mm':'0'}];return p


def selected_options(report,i,j):
    req=report['request'];return {**{k:req[k] for k in ('base_radii','roller_radii','request_id')},'base_index':i,'roller_index':j}


class SizingTests(unittest.TestCase):
    def test_analytic_circle_grid_and_exact_objective_order(self):
        p=circle();before=copy.deepcopy(p)
        result=explore(p,{'base_radii':['30','20','25'],'roller_radii':['6','4'],'max_candidates':64})
        # Any positive radii circle has zero pressure, positive curvature and
        # pitch curvature radius base+roller strictly larger than the roller.
        self.assertTrue(result['complete']);self.assertTrue(result['minimum_within_grid'])
        self.assertEqual([r['status'] for r in result['candidates']],['pass']*6)
        objective=[F(b)+F(r) for b in ['30','20','25'] for r in ['6','4']]
        self.assertEqual([F(r['zero_lift_pitch_radius_mm_exact']) for r in result['candidates']],sorted(objective))
        self.assertEqual((result['selection']['base_index'],result['selection']['roller_index']),(1,1))
        self.assertEqual(p,before)
        tied=explore(p,{'base_radii':['21','20'],'roller_radii':['5','4'],'max_candidates':64})
        self.assertEqual([(x['base_index'],x['roller_index']) for x in tied['candidates']],[(1,1),(1,0),(0,1),(0,0)])

    def test_budget_cancellation_unknown_and_fail_distinctions(self):
        p=circle();options={'base_radii':['20','25'],'roller_radii':['5'],'max_candidates':1}
        result=explore(p,options)
        self.assertEqual(result['status'],'unfinished');self.assertIsNotNone(result['selection']);self.assertFalse(result['minimum_within_grid'])
        calls=[0]
        def cancel():calls[0]+=1;return calls[0]>1
        stopped=explore(p,{**options,'max_candidates':64},cancel=cancel)
        self.assertEqual(stopped['reason'],'cancelled');self.assertEqual(stopped['evaluated'],1);self.assertFalse(stopped['minimum_within_grid'])
        unresolved=explore(example(),{**options,'max_candidates':64},check_budget=1)
        self.assertIn('unknown',[r['status'] for r in unresolved['candidates']]);self.assertFalse(unresolved['minimum_within_grid'])
        cheaper_unknown=explore(example(),{'base_radii':['25','500'],'roller_radii':['5'],'max_candidates':64},check_budget=1)
        self.assertEqual([r['status'] for r in cheaper_unknown['candidates']],['unknown','pass'])
        self.assertIsNotNone(cheaper_unknown['selection']);self.assertFalse(cheaper_unknown['minimum_within_grid'])
        failed=explore(example(),{'base_radii':['20'],'roller_radii':['5'],'max_candidates':64})
        self.assertEqual(failed['outcome'],'no_pass_in_grid');self.assertIsNone(failed['selection'])

    def test_fresh_selection_and_stale_or_forged_status_refusal(self):
        p=example();report=explore(p,{'base_radii':['20','25','30'],'roller_radii':['5'],'max_candidates':64})
        chosen=select(p,selected_options(report,1,0),project_id=identity(p))
        self.assertEqual(chosen['status'],'pass');self.assertTrue(chosen['selection_rechecked'])
        self.assertEqual(chosen['project']['base_radius'],'25')
        # A forged saved Pass is irrelevant: selection always rechecks actual inputs.
        report['candidates'][0]['status']='pass'
        refused=select(p,selected_options(report,0,0),project_id=identity(p))
        self.assertEqual(refused['error']['code'],'selection_refused');self.assertNotIn('project',refused)
        changed=copy.deepcopy(p);changed['base_radius']='25.0'
        stale=select(changed,selected_options(report,1,0),project_id=identity(changed))
        self.assertEqual(stale['error']['code'],'stale_sizing')
        unknown=select(p,selected_options(report,1,0),project_id=identity(p),check_budget=1)
        self.assertEqual(unknown['status'],'unknown');self.assertNotIn('project',unknown)

    def test_admission_and_numeric_duplicate_refusal(self):
        options={'base_radii':['20','25'],'roller_radii':['5'],'max_candidates':64}
        for mutation in ({'base_radii':['25','025']},{'base_radii':[25]},{'max_candidates':True},{'max_candidates':0},
                         {'base_radii':['0']},{'roller_radii':['1e2']},{'extra':True},
                         {'base_radii':[str(i) for i in range(1,10)],'roller_radii':[str(i) for i in range(1,10)]}):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):explore(circle(),{**options,**mutation})
        report=explore(circle(),options)
        with self.assertRaises(ValueError):select(circle(),selected_options(report,True,0),project_id=identity(circle()))
