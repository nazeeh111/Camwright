const $ = id => document.getElementById(id);
const ns = 'http://www.w3.org/2000/svg';
let project, derived = [], history = [], revision = 0, checked = null, dirty = false;
let draftTimer;
let checkBusy = false, focusSnapshot = null, cursorTimer, cursorRevision = 0;
const copy = value => structuredClone(value);
const labels = {pressure:'Pressure limit',convex_pitch:'Strictly convex pitch',roller_curvature:'Local roller curvature'};
const states = {pass:'Pass',fail:'Fail',unknown:'Unresolved'};
function element(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) k === 'class' ? e.className=v : e.setAttribute(k,v);
  for (const child of children) e.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS(ns,tag);
  for (const [k,v] of Object.entries(attrs)) e.setAttribute(k,v);
  return e;
}
function notice(message) { $('notice').textContent=message; $('notice').hidden=!message; }
async function request(path, body, raw) {
  const response = await fetch(path, {method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:raw??JSON.stringify(body)});
  if (!response.ok) {
    let message='Request failed. Your inputs are retained.';
    let failure;
    try { failure=await response.json(); message=failure.error?.message||message; } catch {}
    const error=new Error(message);error.data=failure;throw error;
  }
  return response;
}
function remember() {
  history.push(copy(project)); if(history.length>100)history.shift(); $('undo').disabled=false;
}
function changed() {
  revision++; dirty=true;if(checked){$('stale').textContent='Inputs changed · previous result';$('stale').hidden=false;}
  $('profile-status').textContent=checked?`Stale · previous ${states[checked.result.status]}`:'Not checked';$('profile-status').className='unknown';$('profile-witness').hidden=true;
  $('export').disabled=true; $('export-status').hidden=true;
  clearTimeout(draftTimer);const expected=revision;draftTimer=setTimeout(async()=>{try{const data=await(await request('/api/draft',{project:copy(project)})).json();if(expected===revision)showDerived(data.derived);}catch{}},180);
  $('cursor').disabled=true; $('cursor-values').replaceChildren();
  derived=[];document.querySelectorAll('.derived-start,.derived-motion').forEach(e=>e.textContent='—');
  $('cycle-total').textContent='Cycle edited · validate with Check geometry';
  $('angle-equivalent').textContent='Exact slope; approximate angle shown after checking.';
  notice('');
}
function edit(mutator) { remember(); mutator(); focusSnapshot=null; changed(); renderInputs(); }
function bindInput(input,mutator) {
  input.addEventListener('focus',()=>{focusSnapshot={input,project:copy(project),recorded:false};});
  input.addEventListener('input',()=>{
    if(!focusSnapshot||focusSnapshot.input!==input)focusSnapshot={input,project:copy(project),recorded:false};
    if(!focusSnapshot.recorded){history.push(focusSnapshot.project);if(history.length>100)history.shift();focusSnapshot.recorded=true;$('undo').disabled=false;}
    mutator(input.value); changed();
  });
}
function renderInputs() {
  for(const [id,key] of [['base','base_radius'],['roller','roller_radius'],['slope','maximum_pressure_slope'],['tolerance','tolerance_mm']])$(id).value=project[key];
  $('segments').replaceChildren();
  project.segments.forEach((row,i)=>{
    const span=element('input',{type:'text',inputmode:'decimal',maxlength:'32','aria-label':`Segment ${i+1} span in degrees`});span.value=row.span_deg;bindInput(span,v=>project.segments[i].span_deg=v);
    const end=element('input',{type:'text',inputmode:'decimal',maxlength:'32','aria-label':`Segment ${i+1} end lift in millimetres`});end.value=row.end_mm;bindInput(end,v=>project.segments[i].end_mm=v);
    const controls=element('div',{class:'row-actions'});
    for(const [text,label,delta] of [['↑','Move segment up',-1],['↓','Move segment down',1]]){
      const b=element('button',{'aria-label':`${label}: segment ${i+1}`,title:label},text);b.disabled=i+delta<0||i+delta>=project.segments.length;
      b.addEventListener('click',()=>edit(()=>{[project.segments[i],project.segments[i+delta]]=[project.segments[i+delta],project.segments[i]];}));controls.append(b);
    }
    const remove=element('button',{'aria-label':`Remove segment ${i+1}`,title:'Remove segment'},'×');remove.disabled=project.segments.length<=1;
    remove.addEventListener('click',()=>edit(()=>project.segments.splice(i,1)));controls.append(remove);
    const d=derived[i];
    $('segments').append(element('tr',{},element('td',{},String(i+1)),element('td',{},span),element('td',{},end),element('td',{class:'derived-start'},d?.start_deg_exact??'—'),element('td',{class:'derived-motion'},d?.motion??d?.kind??'—'),element('td',{},controls)));
  });
  $('add').disabled=project.segments.length>=12;
}
function showDerived(data) {
  derived=data?.segments||[];
  [...$('segments').children].forEach((row,i)=>{row.querySelector('.derived-start').textContent=derived[i]?.start_deg_exact??'—';row.querySelector('.derived-motion').textContent=derived[i]?.motion??derived[i]?.kind??'—';});
  $('cycle-total').textContent=`${data?.total_deg_exact??'360'}° · ${data?.remaining_deg_exact??'0'}° remaining · end lift ${derived.at(-1)?.end_mm_exact??'0'} mm`;
}
function replaceProject(next,data,saved=false) {
  if(project)remember();project=copy(next);derived=data?.segments||[];revision++;checked=null;dirty=!saved;focusSnapshot=null;
  renderInputs();showDerived(data);for(const id of ['base','roller','slope','tolerance','save','example'])$(id).disabled=false;$('check').disabled=checkBusy;$('undo').disabled=!history.length;$('overall').textContent='Not checked';$('overall').className='';$('profile-status').textContent='Not checked';$('profile-status').className='';$('profile-witness').hidden=true;$('stale').hidden=true;
  $('check-details').textContent='Check the current motion cycle and dimensions.';$('export').disabled=true;$('cursor').disabled=true;$('cursor').value=0;$('cursor-angle').value='0°';
  $('angle-equivalent').textContent='Exact slope; approximate angle shown after checking.';$('cursor-values').replaceChildren();$('profile').replaceChildren(svg('text',{x:260,y:210,'text-anchor':'middle'}));$('profile').firstChild.textContent='Check geometry to draw the profile.';$('displacement').replaceChildren();$('export-status').hidden=true;
}
function approximate(value){const parts=String(value).split('/');return Number(parts[0])/(parts.length>1?Number(parts[1]):1);}
function resultCards(result) {
  $('overall').textContent=states[result.status]||'Unresolved';$('overall').className=result.status;
  $('profile-status').textContent=`${states[result.status]||'Unresolved'} · geometry`;$('profile-status').className=result.status;
  const issue=result.segments.flatMap(s=>Object.entries(s.checks).map(([key,item])=>({key,item,segment:s.segment}))).find(x=>x.item.status===result.status&&x.item.status!=='pass');
  $('profile-witness').hidden=!issue;if(issue){const a=issue.item.angle_deg??issue.item.angle_interval_deg?.[0];$('profile-witness').textContent=`${labels[issue.key]} · segment ${issue.segment+1} · ${issue.item.angle_deg!==undefined?'witness':'interval'} ${issue.item.angle_deg??issue.item.angle_interval_deg?.join('–')??''}°`;$('profile-witness').onclick=()=>{if(a!==undefined)setCursor(approximate(a));$('cursor').scrollIntoView({block:'center',behavior:'smooth'});};}
  $('check-details').replaceChildren();
  for(const [key,label] of Object.entries(labels)){
    const card=element('div',{class:'check-card'},element('h3',{},label));
    for(const segment of result.segments){
      const item=segment.checks[key], state=states[item.status]||'Unresolved';
      const row=element('div',{class:'check-row'},element('span',{},`Segment ${segment.segment+1}`),element('strong',{class:item.status},state));card.append(row);
      if(item.status==='pass')card.append(element('p',{class:'hint'},`Continuous interval check · ${item.boxes} intervals examined.`));
      if(item.status!=='pass'){
        const angle=item.angle_deg??item.angle_interval_deg?.[0];
        const text=item.angle_deg!==undefined?`Witness ${item.angle_deg}°`:item.angle_interval_deg?`Interval ${item.angle_interval_deg.join('–')}°`:'Unresolved interval';
        const b=element('button',{},text);b.disabled=angle===undefined;b.addEventListener('click',()=>setCursor(approximate(angle)));card.append(b);
        const reason=(item.reason==='work_or_depth_limit'?'Subdivision work or depth limit reached.':item.reason)||(item.status==='fail'?'The geometric condition fails.':'Subdivision work or depth limit reached.');card.append(element('p',{class:'hint'},`${reason} Work: ${item.boxes}.`));
      }
    }
    $('check-details').append(card);
  }
}
let plotMap;
function drawPreview(preview) {
  const points=preview.points, profile=$('profile'), displacement=$('displacement');profile.replaceChildren();displacement.replaceChildren();
  const all=points.flatMap(p=>[p.cam,p.pitch]);const extent=Math.max(1,...all.flat().map(Math.abs));
  const scale=175/extent, cx=260,cy=210;plotMap={scale,cx,cy};
  for(const [x1,y1,x2,y2] of [[40,cy,480,cy],[cx,20,cx,400]])profile.append(svg('line',{x1,y1,x2,y2,stroke:'#dce1e7','stroke-width':1}));
  for(const [text,x,y] of [['+X',481,cy-7],['+Y',cx+8,18],['0',cx+7,cy+16]]){const t=svg('text',{x,y});t.textContent=text;profile.append(t);}
  const path=key=>points.map((p,i)=>`${i?'L':'M'}${cx+p[key][0]*scale},${cy-p[key][1]*scale}`).join(' ')+' Z';
  profile.append(svg('path',{d:path('pitch'),fill:'none',stroke:'#7c8793','stroke-width':1.6,'stroke-dasharray':'6 4'}),svg('path',{d:path('cam'),fill:'none',stroke:'#252b33','stroke-width':2}),svg('circle',{cx,cy,r:3,fill:'#252b33'}));
  const lift=Math.max(1,...points.map(p=>p.lift_mm));const dx=a=>42+a/360*456,dy=s=>153-s/lift*125;
  for(const a of [0,90,180,270,360]){const x=dx(a);displacement.append(svg('line',{x1:x,y1:20,x2:x,y2:153,stroke:'#e4e7eb'}));const t=svg('text',{x,y:175,'text-anchor':'middle'});t.textContent=`${a}°`;displacement.append(t);}
  for(const y of [0,lift/2,lift]){const t=svg('text',{x:35,y:dy(y)+4,'text-anchor':'end'});t.textContent=y.toFixed(2);displacement.append(t);}
  displacement.append(svg('path',{d:points.map((p,i)=>`${i?'L':'M'}${dx(p.angle_deg)},${dy(p.lift_mm)}`).join(' '),fill:'none',stroke:'#252b33','stroke-width':2}));
  plotMap.dx=dx;plotMap.dy=dy;$('cursor').disabled=false;setCursor(0);
}
async function setCursor(angle) {
  if(!checked||checked.revision!==revision)return;
  $('cursor').value=angle;$('cursor-angle').value=`${Number(angle.toFixed(4))}°`;
  [...$('segments').children].forEach((row,i)=>row.classList.toggle('active-segment',angle>=approximate(derived[i]?.start_deg_exact??0)&&angle<approximate(derived[i]?.end_deg_exact??0)));
  clearTimeout(cursorTimer);const token=++cursorRevision,expected=revision;
  cursorTimer=setTimeout(async()=>{try{
    const p=await(await request('/api/point',{project:checked.project,angle_deg:angle.toFixed(12).replace(/\.?0+$/,'')||'0'})).json();
    if(token!==cursorRevision||expected!==revision)return;
    for(const id of ['roller-overlay','displacement-cursor'])$(id)?.remove();
    const {scale,cx,cy,dx,dy}=plotMap;
    const g=svg('g',{id:'roller-overlay'}),px=cx+p.pitch[0]*scale,py=cy-p.pitch[1]*scale,qx=cx+p.cam[0]*scale,qy=cy-p.cam[1]*scale;
    g.append(svg('line',{x1:cx,y1:cy,x2:px,y2:py,stroke:'#506d87','stroke-width':1}),svg('circle',{cx:px,cy:py,r:p.roller_radius_mm*scale,fill:'none',stroke:'#506d87','stroke-width':1.5}),svg('line',{x1:qx,y1:qy,x2:px,y2:py,stroke:'#506d87','stroke-dasharray':'3 2'}),svg('circle',{cx:qx,cy:qy,r:3,fill:'#506d87'}),svg('circle',{cx:px,cy:py,r:2,fill:'#506d87'}));$('profile').append(g);
    const c=svg('g',{id:'displacement-cursor'});c.append(svg('line',{x1:dx(angle),y1:20,x2:dx(angle),y2:153,stroke:'#506d87','stroke-dasharray':'3 2'}),svg('circle',{cx:dx(angle),cy:dy(p.lift_mm),r:3,fill:'#506d87'}));$('displacement').append(c);
    $('cursor-values').replaceChildren(element('span',{},`Lift ${p.lift_mm.toFixed(3)} mm`),element('span',{},`Center (${p.pitch.map(v=>v.toFixed(3)).join(', ')}) mm`),element('span',{},`Contact (${p.cam.map(v=>v.toFixed(3)).join(', ')}) mm`),element('span',{},`Roller R ${p.roller_radius_mm} mm`));
  }catch(error){if(expected===revision)notice(`Cursor: ${error.message}`);}},80);
}
function download(blob,name){const url=URL.createObjectURL(blob),a=element('a',{href:url,download:name});document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
async function validate(raw) {return(await request('/api/validate',{project},raw)).json();}
$('check').addEventListener('click',async()=>{
  if(checkBusy)return;const current=copy(project),expected=revision;checkBusy=true;$('check').disabled=true;$('check').textContent='Checking…';$('export').disabled=true;notice('');$('profile-status').textContent='Checking geometry…';$('profile-status').className='unknown';$('profile-witness').hidden=true;if(checked){$('stale').textContent='Checking · previous result';$('stale').hidden=false;}
  try{
    const data=await(await request('/api/check',{project:current})).json();
    if(expected!==revision){notice('Inputs changed during checking. Check the current draft.');return;}
    checked={...data,revision:expected,project:current};showDerived(data.derived);resultCards(data.result);drawPreview(data.preview);$('stale').hidden=true;
    $('angle-equivalent').textContent=`≈ ${data.result.pressure_angle_limit_deg_approx.toFixed(3)}° (display only)`;
    $('export').disabled=data.result.status!=='pass';
  }catch(error){notice(error.message);$('profile-status').textContent=checked?`Stale · previous ${states[checked.result.status]}`:'Not checked';$('profile-status').className='unknown';if(checked){$('stale').textContent='Check failed · previous result';$('stale').hidden=false;}}finally{checkBusy=false;$('check').disabled=false;$('check').textContent='Check geometry';}
});
$('cursor').addEventListener('input',()=>setCursor(Number($('cursor').value)));
for(const id of ['profile','displacement'])$(id).addEventListener('pointerdown',event=>{
  if(!checked||checked.revision!==revision)return;
  const rect=$(id).getBoundingClientRect(),x=(event.clientX-rect.left)*520/rect.width,y=(event.clientY-rect.top)*(id==='profile'?420:190)/rect.height;
  const points=checked.preview.points;
  const distance=p=>id==='profile'?(plotMap.cx+p.cam[0]*plotMap.scale-x)**2+(plotMap.cy-p.cam[1]*plotMap.scale-y)**2:Math.abs(plotMap.dx(p.angle_deg)-x);
  const closest=points.reduce((a,b)=>distance(a)<distance(b)?a:b);setCursor(closest.angle_deg);
});
for(const [id,key] of [['base','base_radius'],['roller','roller_radius'],['slope','maximum_pressure_slope'],['tolerance','tolerance_mm']])bindInput($(id),value=>project[key]=value);
$('add').addEventListener('click',()=>edit(()=>project.segments.push({span_deg:'30',end_mm:'0'})));
$('undo').addEventListener('click',()=>{if(!history.length)return;project=history.pop();focusSnapshot=null;derived=[];changed();renderInputs();$('undo').disabled=!history.length;});
$('save').addEventListener('click',async()=>{const expected=revision;try{const data=await validate();if(expected!==revision){notice('Inputs changed. Save the current draft again.');return;}download(new Blob([JSON.stringify(data.project,null,2)+'\n'],{type:'application/json'}),'camwright-project.json');dirty=false;notice('Project downloaded.');}catch(error){notice(error.message);}});
$('open').addEventListener('click',()=>{$('file').value='';$('file').click();});
$('file').addEventListener('change',async()=>{
  const file=$('file').files[0];if(!file)return;if(file.size>32768){notice('Project exceeds 32 KiB. Current inputs are retained.');return;}
  const expected=revision;try{const text=await file.text(),data=await validate('{"project":'+text+'}');if(expected!==revision){notice('Inputs changed while opening. Select the file again.');return;}replaceProject(data.project,data.derived,true);notice('Project opened. Check geometry to update the profile.');}catch(error){notice(error.message);}
});
$('example').addEventListener('click',async()=>{if(dirty&&!confirm('Replace the current draft with the example? Save project first to keep it.'))return;const expected=revision;try{const data=await(await request('/api/example')).json();const valid=await(await request('/api/validate',{project:data.project??data})).json();if(expected!==revision){notice('Inputs changed while loading the example. Current draft retained.');return;}replaceProject(valid.project,valid.derived,true);notice('Example loaded.');}catch(error){notice(error.message);}});
$('export').addEventListener('click',async()=>{
  if(!checked||checked.revision!==revision||checked.result.status!=='pass')return;
  const expected=revision;$('export').disabled=true;$('export').textContent='Bounding export…';$('export-status').hidden=true;notice('');
  try{const response=await request('/api/export',{project:copy(project),project_id:checked.project_id});const blob=await response.blob();if(expected!==revision){notice('Inputs changed during export. No file downloaded. Check the current draft.');return;}download(blob,'camwright-profile.zip');$('export-status').textContent=`Export Pass · ${response.headers.get('X-Camwright-Vertices')} vertices · physical bound ${response.headers.get('X-Camwright-Cam-Bound-Mm')} mm · pitch bound ${response.headers.get('X-Camwright-Pitch-Bound-Mm')} mm. ZIP includes exact project and certificates.`;$('export-status').hidden=false;}catch(error){notice(error.message);$('export-status').textContent=`Export ${states[error.data?.status]||'refused'} · no geometry downloaded.`;$('export-status').hidden=false;}finally{$('export').textContent='Export profile ZIP';$('export').disabled=!checked||checked.revision!==revision||checked.result.status!=='pass';}
});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
document.querySelectorAll('.inputs input,.inputs button,#save,#undo,#example').forEach(e=>e.disabled=true);
(async()=>{try{const data=await(await request('/api/example')).json();const valid=await(await request('/api/validate',{project:data.project??data})).json();replaceProject(valid.project,valid.derived,true);$('check').click();}catch(error){notice(error.message);$('check').disabled=true;$('example').disabled=false;}})();
