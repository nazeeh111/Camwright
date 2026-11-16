import base64,csv,io,json,math,unittest,zipfile
from decimal import Decimal as D,localcontext
from fractions import Fraction as F
from camwright.engine import calculate
from camwright.project import identity
from .test_sizing import example,circle


def trig(theta):
    sin=term=theta;cos=cterm=D(1)
    for n in range(1,65):
        term*=-theta*theta/D((2*n)*(2*n+1));sin+=term
        cterm*=-theta*theta/D((2*n-1)*(2*n));cos+=cterm
    return cos,sin


def independent_curve(p,angle,name):
    # High-precision Cartesian tangent and its clockwise unit normal.
    pi=D('3.1415926535897932384626433832795028841971693993751058209749445923078164')
    angle%=360;start=F(0);height=D(0)
    for row in p['segments']:
        span=F(row['span_deg']);end=D(row['end_mm'])
        if start<=angle<start+span:
            u=D((angle-start).numerator)/D((angle-start).denominator)/(D(span.numerator)/D(span.denominator))
            delta=end-height;r=D(p['base_radius'])+D(p['roller_radius'])+height+delta*(10*u**3-15*u**4+6*u**5)
            v=delta*(30*u**2-60*u**3+30*u**4)/(D(span.numerator)/D(span.denominator)*pi/180)
            theta=D(angle.numerator)/D(angle.denominator)*pi/180;c,s=trig(theta)
            point=(r*c,r*s)
            if name=='pitch':return point
            tangent=(v*c-r*s,v*s+r*c);length=(tangent[0]**2+tangent[1]**2).sqrt();roller=D(p['roller_radius'])
            return point[0]-roller*tangent[1]/length,point[1]+roller*tangent[0]/length
        start+=span;height=end
    raise AssertionError('Angle outside closed motion')


def dxf_vertices(data):
    lines=data.decode().splitlines();pairs=list(zip(map(int,lines[::2]),lines[1::2]))
    assert pairs[-1]==(0,'EOF')
    assert (9,'$INSUNITS') in pairs and pairs[pairs.index((9,'$INSUNITS'))+1]==(70,'4')
    start=pairs.index((0,'LWPOLYLINE'));entity=pairs[start:]
    assert (70,'1') in entity and (210,'0') in entity and (220,'0') in entity and (230,'1') in entity
    vertices=[]
    for i,(code,value) in enumerate(entity):
        if code==10:
            assert entity[i+1][0]==20;vertices.append((value,entity[i+1][1]))
    assert (90,str(len(vertices))) in entity
    return vertices


class HandoffTests(unittest.TestCase):
    def test_exact_dxf_csv_vertices_and_independent_decimal_curve_bounds(self):
        p=example();result=calculate('export',p,identity(p));self.assertEqual(result['summary']['cad_status'],'pass')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['zip_base64']))) as archive:
            report=json.loads(archive.read('export.json'))
            with localcontext() as context:
                context.prec=65
                for name in ('cam','pitch'):
                    rows=list(csv.DictReader(io.StringIO(archive.read(name+'.csv').decode())))
                    vertices=dxf_vertices(archive.read(name+'.dxf'))
                    self.assertEqual(vertices,[(r['x_mm'],r['y_mm']) for r in rows[:-1]])
                    for i,cell in enumerate(report['intervals']):
                        a,b=F(cell['start_deg_exact']),F(cell['end_deg_exact']);left=tuple(D(rows[i][k]) for k in ('x_mm','y_mm'));right=tuple(D(rows[i+1][k]) for k in ('x_mm','y_mm'))
                        for fraction in (F(0),F(17,100),F(43,100),F(81,100),F(1)):
                            actual=independent_curve(p,a+(b-a)*fraction,name);t=D(fraction.numerator)/D(fraction.denominator)
                            linear=tuple(x+(y-x)*t for x,y in zip(left,right));error=sum((x-y)**2 for x,y in zip(actual,linear)).sqrt()
                            self.assertLessEqual(error,D(cell[name+'_bound_mm'])+D('1e-50'))

    def test_tiny_coarse_profile_retains_legacy_formats_without_fabricated_cad(self):
        p=circle();p.update(base_radius='0.001',roller_radius='0.001',tolerance_mm='1')
        result=calculate('export',p,identity(p));self.assertEqual(result['status'],'pass');self.assertEqual(result['summary']['cad_status'],'unavailable')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['zip_base64']))) as archive:
            self.assertNotIn('cam.dxf',archive.namelist());self.assertIn('cam.csv',archive.namelist())
            self.assertEqual(json.loads(archive.read('export.json'))['dxf']['status'],'unavailable')
