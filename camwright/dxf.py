"""ASCII DXF linear entities consume only already-certified CSV decimals."""
import csv
from fractions import Fraction
import io


class UnrepresentablePolyline(ValueError):
    """Certified approximation is too coarse/degenerate for a closed CAD face."""


def from_csv(text, *, layer):
    rows=list(csv.DictReader(io.StringIO(text)))
    if len(rows)<2 or (rows[0]['x_mm'],rows[0]['y_mm'])!=(rows[-1]['x_mm'],rows[-1]['y_mm']):
        raise ValueError('Certified curve must close at its shared endpoint')
    vertices=[(row['x_mm'],row['y_mm']) for row in rows[:-1]]
    area=sum(Fraction(x)*Fraction(v)-Fraction(u)*Fraction(y)
             for (x,y),(u,v) in zip(vertices,vertices[1:]+vertices[:1]))
    if len(vertices)<3 or len(set(vertices))<3 or area<=0:
        raise UnrepresentablePolyline('Emitted vertices do not form a nondegenerate counterclockwise closed CAD polyline')
    pairs=[(0,'SECTION'),(2,'HEADER'),(9,'$ACADVER'),(1,'AC1015'),(9,'$INSUNITS'),(70,4),
           (9,'$MEASUREMENT'),(70,1),(0,'ENDSEC'),(0,'SECTION'),(2,'ENTITIES'),
           (0,'LWPOLYLINE'),(100,'AcDbEntity'),(8,layer),(100,'AcDbPolyline'),
           (90,len(vertices)),(70,1),(38,0),(210,0),(220,0),(230,1)]
    for x,y in vertices:pairs.extend(((10,x),(20,y)))
    pairs.extend(((0,'ENDSEC'),(0,'EOF')))
    return ''.join(f'{code}\n{value}\n' for code,value in pairs)
