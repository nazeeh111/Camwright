"""Render exact native check/grid records and every emitted CSV vertex.
2D Cartesian geometry uses one uniform mm-to-screen scale, with +Y upward.
No failed profile geometry is exported or invented for the left-hand evidence.
"""
from pathlib import Path
import json,csv,html,hashlib,math
P=Path(__file__).resolve().parent;failure=json.loads((P/'failed-check.json').read_text());grid=json.loads((P/'radius-grid.json').read_text());selected=json.loads((P/'selected-project.json').read_text());meta=json.loads((P/'export.json').read_text());cam=[(float(r['x_mm']),float(r['y_mm'])) for r in csv.DictReader((P/'cam.csv').open())];pitch=[(float(r['x_mm']),float(r['y_mm'])) for r in csv.DictReader((P/'pitch.csv').open())];assert len(cam)==len(pitch)==meta['vertices']==261;assert failure['result']['status']=='fail';w=failure['result']['segments'][0]['checks']['pressure'];assert w['angle_deg']=='60' and w['u']=='1/2';assert grid['minimum_within_grid'] and len(grid['candidates'])==9;roller=float(selected['roller_radius']);assert selected['base_radius']=='25' and selected['roller_radius']=='4';assert cam[0]==(25.,0.) and pitch[0]==(29.,0.);records=[]
def draw(phone):
 W,H=(420,1450) if phone else (1280,880);m=28 if phone else 44;parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">','<title id="title">Camwright: save the failed check, export the checked curve</title>','<desc id="desc">Actual 20/5 mm cam fails pressure at cam angle 60 degrees, yet its inspection can be saved. All 9 radius pairs classify 3 Fail and 6 Pass; 25/4 mm has minimum 29 mm zero-lift pitch radius within this grid. All 261 emitted vertices of each physical and pitch curve and the 4 mm roller at zero angle are drawn at equal scale. Model bounds do not establish machining fitness.</desc>','<style>text{font-family:Arial,Helvetica,sans-serif;fill:#24384b}.muted{fill:#536372}.fail{fill:#963c40}.pass{fill:#315542}.accent{fill:#a85d20}</style>',f'<rect width="{W}" height="{H}" fill="#f4f6f8"/>']
 def t(x,y,text,size=20,cls='',weight=400):parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" class="{cls}">{html.escape(str(text))}</text>')
 t(m,48,'Camwright / CHECK → SELECT → EXPORT',18,weight=700)
 if phone:t(m,108,'Keep the failed check.',29,weight=700);t(m,149,'Export the checked curve.',28,weight=700);t(m,190,'Actual records. Finite grid. Native CAD.',16,'muted')
 else:t(m,116,'Keep the failed check. Export the checked curve.',43,weight=700);t(m,164,'One completed geometry-workbench journey, with the exact inspection and native profile artifacts.',20,'muted')
 fx,fy=(m,248) if phone else (44,260);t(fx,fy,'20 / 5 mm: Fail',26,'fail',700);t(fx,fy+49,'Cam-angle witness: 60°',20,weight=700);t(fx,fy+86,'Exact segment parameter u = 1/2',16,'muted');t(fx,fy+121,'Pressure slope limit: 0.5',17,'muted');t(fx,fy+152,'Approximate limit: 26.565°',17,'muted');t(fx,fy+198,'Inspection saved. Geometry blocked.',18,'fail',700)
 gx,gy,cw,ch=(96,568,86,62) if phone else (461,332,87,75);t(m if phone else 420,510 if phone else 260,'Nine pairs. Every status retained.',22,weight=700);t(m if phone else 420,541 if phone else 296,'Roller radius / mm',16,'muted')
 for j,r in enumerate(['4','5','6']):t(gx+j*cw+cw/2-5,gy-12,r,17)
 for i,b in enumerate(['20','25','30']):
  t(gx-37,gy+i*ch+ch/2+5,b,17)
  for j,r in enumerate(['4','5','6']):
   row=next(q for q in grid['candidates'] if q['base_radius']==b and q['roller_radius']==r);x,y=gx+j*cw,gy+i*ch;chosen=b=='25' and r=='4';parts.append(f'<rect class="grid-cell" data-base="{b}" data-roller="{r}" x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{("#e6eee7" if row["status"]=="pass" else "#f2e7e8")}" stroke="{("#a85d20" if chosen else "#ccd4dc")}" stroke-width="{3 if chosen else 1}"/>');t(x+13,y+24,row['status'].upper(),15,'pass' if row['status']=='pass' else 'fail',700);t(x+13,y+48,row['zero_lift_pitch_radius_mm_exact']+' mm',16)
 t(m if phone else 420,gy+3*ch+37,'Pitch radius = base + roller',16,'muted');t(m if phone else 420,gy+3*ch+71,'Minimum within this grid: 29 mm',19,'accent',700)
 px,py,pw,ph=(42,937,336,333) if phone else (820,258,412,412);t(m if phone else 820,899 if phone else 224,'Selected 25 / 4 mm profile',23,weight=700)
 points=cam+pitch+[(pitch[0][0]-roller,-roller),(pitch[0][0]+roller,roller)];lo=[min(p[i] for p in points) for i in (0,1)];hi=[max(p[i] for p in points) for i in (0,1)];scale=min((pw-34)/(hi[0]-lo[0]),(ph-34)/(hi[1]-lo[1]));ox=px+17+(pw-34-(hi[0]-lo[0])*scale)/2;oy=py+17+(ph-34-(hi[1]-lo[1])*scale)/2
 def xy(p):return ox+(p[0]-lo[0])*scale,oy+(hi[1]-p[1])*scale
 for axis in (0,1):
  a,b=xy((lo[0],0) if axis==0 else (0,lo[1])),xy((hi[0],0) if axis==0 else (0,hi[1]));parts.append(f'<path d="M{a[0]:.5f},{a[1]:.5f}L{b[0]:.5f},{b[1]:.5f}" stroke="#c0cbd5" stroke-width="1"/>')
 for name,values,color,dash in [('pitch',pitch,'#8395a7','5 5'),('cam',cam,'#24384b','')]:
  coords=' '.join(f'{a:.5f},{b:.5f}' for a,b in map(xy,values));parts.append(f'<polyline id="{name}" points="{coords}" fill="none" stroke="{color}" stroke-width="{1.2 if name=="pitch" else 2.4}" stroke-dasharray="{dash}"/>')
 cx,cy=xy(pitch[0]);parts.append(f'<circle id="roller" cx="{cx:.5f}" cy="{cy:.5f}" r="{roller*scale:.5f}" fill="#fff6ec" stroke="#a85d20" stroke-width="2"/>');a,b=xy(cam[0]);parts.append(f'<circle id="contact" cx="{a:.5f}" cy="{b:.5f}" r="3" fill="#a85d20"/>');t(px,py+ph+30,'Solid: cam · dashed: roller-centre path',15,'muted');t(px,py+ph+58,'4 mm roller shown at cam angle 0°',15,'accent');t(px,py+ph+87,'Equal spatial scale · millimetres · +Y up',15,'muted')
 if phone:t(m,1395,'Cam deviation bound < 0.009938 mm.',17,weight=700);t(m,1430,'Geometric model; not machining approval.',16,'muted')
 else:t(m,785,'261 emitted vertices · 0.01 mm requested deviation · cam bound < 0.009938 mm · native DXF reopened',22,weight=700);t(m,839,'The minimum is only within the declared nine-pair grid. Geometry and approximation checks do not establish loads, wear or machining fitness.',17,'muted')
 parts.append('</svg>');records.append({'figure':'phone' if phone else 'desktop','mmToScreenScale':scale,'lo_mm':lo,'hi_mm':hi,'origin':[ox,oy],'screenYUsesMinusWorldY':True,'all261VerticesPerCurve':True});return '\n'.join(parts)+'\n'
for name,phone in [('inspection-to-profile',False),('inspection-to-profile-mobile',True)]:(P/(name+'.svg')).write_text(draw(phone))
(P/'figure-data.json').write_text(json.dumps({'case':'finite9','views':records,'camVertices':len(cam),'pitchVertices':len(pitch),'rollerRadius_mm':roller,'firstContact_mm':cam[0],'rollerCentre_mm':pitch[0],'failedCamAngle_deg':'60'},indent=2)+'\n')
