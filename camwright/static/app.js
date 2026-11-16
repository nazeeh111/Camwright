const $ = id => document.getElementById(id);
const ns = 'http://www.w3.org/2000/svg';
let project, derived = [], history = [], revision = 0, checked = null, dirty = false;
let draftTimer;
let checkBusy = false, focusSnapshot = null, cursorTimer, cursorRevision = 0;
let inspectionBusy = false, exportBusy = false;
let gridEpoch = 0, gridReport = null, gridReportRevision = -1, gridReportEpoch = -1, gridReportKey = null, gridOperation = null;
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
function updateInspectionButton() {
  $('inspection').disabled=inspectionBusy||checkBusy||exportBusy||!!gridOperation||!checked?.inspection_id||checked.revision!==revision;
}
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
  $('check-announcement').textContent='';
  $('profile-status').textContent=checked?`Stale · previous ${states[checked.result.status]}`:'Not checked';$('profile-status').className='unknown';$('profile-witness').hidden=true;
  $('export').disabled=true; $('export-status').hidden=true;
  updateInspectionButton();
  clearTimeout(draftTimer);const expected=revision;draftTimer=setTimeout(async()=>{try{const data=await(await request('/api/draft',{project:copy(project)})).json();if(expected===revision)showDerived(data.derived);}catch{}},180);
  $('cursor').disabled=true; $('cursor-values').replaceChildren();
  derived=[];document.querySelectorAll('.derived-start,.derived-motion').forEach(e=>e.textContent='—');
  $('cycle-total').textContent='Cycle edited · validate with Check geometry';
  $('angle-equivalent').textContent='Exact slope; approximate angle shown after checking.';
  notice('');invalidateGrid();
}
function edit(mutator, focusTarget) {
  remember(); mutator(); focusSnapshot=null; changed(); renderInputs();
  if(focusTarget){
    const row=$('segments').children[Math.min(focusTarget.index,project.segments.length-1)];
    const preferred=row?.querySelector(`[data-control="${focusTarget.control}"]`);
    (preferred&&!preferred.disabled?preferred:row?.querySelector('input'))?.focus();
  }
}
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
      const control=delta<0?'move-up':'move-down';
      const b=element('button',{'aria-label':`${label}: segment ${i+1}`,title:label,'data-control':control},text);b.disabled=i+delta<0||i+delta>=project.segments.length;
      b.addEventListener('click',()=>edit(()=>{[project.segments[i],project.segments[i+delta]]=[project.segments[i+delta],project.segments[i]];},{index:i+delta,control}));controls.append(b);
    }
    const remove=element('button',{'aria-label':`Remove segment ${i+1}`,title:'Remove segment','data-control':'remove'},'×');remove.disabled=project.segments.length<=1;
    remove.addEventListener('click',()=>edit(()=>project.segments.splice(i,1),{index:i,control:'remove'}));controls.append(remove);
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
  $('check-announcement').textContent='';
  $('check-details').textContent='Check the current motion cycle and dimensions.';$('export').disabled=true;$('cursor').disabled=true;$('cursor').value=0;$('cursor-angle').value='0°';
  updateInspectionButton();
  $('angle-equivalent').textContent='Exact slope; approximate angle shown after checking.';$('cursor-values').replaceChildren();$('profile').replaceChildren(svg('text',{x:260,y:210,'text-anchor':'middle'}));$('profile').firstChild.textContent='Check geometry to draw the profile.';$('displacement').replaceChildren();$('export-status').hidden=true;invalidateGrid();
}
function approximate(value){const parts=String(value).split('/');return Number(parts[0])/(parts.length>1?Number(parts[1]):1);}
function witnessText(item) {
  return item.angle_deg!==undefined?`Witness ${item.angle_deg}°`:item.angle_interval_deg?`Interval ${item.angle_interval_deg.join('–')}°`:'Unresolved interval';
}
function witnessLabel(key, segment, item) {
  return `${labels[key]} · segment ${segment+1} · ${witnessText(item)}`;
}
function showWitness(item) {
  if(checkBusy||!checked||checked.revision!==revision)return;
  const angle=item.angle_deg??item.angle_interval_deg?.[0];
  if(angle===undefined)return;
  setCursor(approximate(angle));
  $('cursor').focus({preventScroll:true});
  $('drawing-heading').scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
}
function announceResult(result) {
  const checks=result.segments.flatMap(segment=>Object.values(segment.checks));
  const failed=checks.filter(item=>item.status==='fail').length;
  const unresolved=checks.filter(item=>item.status==='unknown').length;
  const outcome=result.status==='pass'?`All ${checks.length} checks passed.`:`${failed} failed checks; ${unresolved} unresolved checks.`;
  $('check-announcement').textContent=`Geometry check complete: ${states[result.status]||'Unresolved'}. ${outcome} ${result.segments.length} motion segments. ${result.status==='pass'?'Profile export can now be requested.':'Profile export unavailable.'}`;
}
function renderResults(result) {
  $('overall').textContent=states[result.status]||'Unresolved';$('overall').className=result.status;
  $('profile-status').textContent=`${states[result.status]||'Unresolved'} · geometry`;$('profile-status').className=result.status;
  const issue=result.segments.flatMap(s=>Object.entries(s.checks).map(([key,item])=>({key,item,segment:s.segment}))).find(x=>x.item.status===result.status&&x.item.status!=='pass');
  $('profile-witness').hidden=!issue;if(issue){$('profile-witness').textContent=witnessLabel(issue.key,issue.segment,issue.item);$('profile-witness').setAttribute('aria-label',witnessLabel(issue.key,issue.segment,issue.item));$('profile-witness').disabled=(issue.item.angle_deg??issue.item.angle_interval_deg?.[0])===undefined;$('profile-witness').onclick=()=>showWitness(issue.item);}
  $('check-details').replaceChildren();
  const header=()=>element('thead',{},element('tr',{},element('th',{scope:'col'},'Segment'),...Object.values(labels).map(label=>element('th',{scope:'col'},label))));
  const body=element('tbody'), evidenceBody=element('tbody');
  const table=element('table',{class:'check-matrix'},header(),body);
  const evidenceTable=element('table',{class:'check-evidence'},header(),evidenceBody);
  for(const segment of result.segments){
    const row=element('tr',{},element('th',{scope:'row'},`Segment ${segment.segment+1}`));
    const evidenceRow=element('tr',{},element('th',{scope:'row'},`Segment ${segment.segment+1}`));
    for(const key of Object.keys(labels)){
      const item=segment.checks[key];
      const cell=element('td',{},element('strong',{class:item.status},states[item.status]||'Unresolved'));
      if(item.status!=='pass'){
        const angle=item.angle_deg??item.angle_interval_deg?.[0];
        const button=element('button',{'aria-label':witnessLabel(key,segment.segment,item)},witnessText(item));
        button.disabled=angle===undefined;button.addEventListener('click',()=>showWitness(item));cell.append(button);
        const reason=(item.reason==='work_or_depth_limit'?'Subdivision work or depth limit reached.':item.reason)||(item.status==='fail'?'The geometric condition fails.':'Subdivision work or depth limit reached.');cell.append(element('p',{class:'hint'},`${reason} Work: ${item.boxes}.`));
      }
      row.append(cell);
      evidenceRow.append(element('td',{},`${states[item.status]||'Unresolved'} · ${item.boxes} intervals examined`));
    }
    body.append(row);evidenceBody.append(evidenceRow);
  }
  const scroll=element('div',{class:'table-scroll',tabindex:'0',role:'region','aria-label':'Geometric checks by motion segment. Scroll horizontally on narrow screens.'},table);
  const evidence=element('details',{class:'result-evidence'},element('summary',{},'Continuous-check evidence'),element('p',{class:'hint'},'Subdivision intervals examined for each continuous-angle check. Saved inspections retain the exact inputs and certificates.'),element('div',{class:'table-scroll',tabindex:'0',role:'region','aria-label':'Continuous-check subdivision counts. Scroll horizontally on narrow screens.'},evidenceTable));
  $('check-details').append(scroll,evidence);
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
  if(checkBusy||gridOperation||exportBusy)return;const current=copy(project),expected=revision;checkBusy=true;$('check').disabled=true;$('check').textContent='Checking…';$('export').disabled=true;notice('');$('profile-status').textContent='Checking geometry…';$('profile-status').className='unknown';$('profile-witness').hidden=true;if(checked){$('stale').textContent='Checking · previous result';$('stale').hidden=false;}
  $('check-announcement').textContent='';
  if(checked)checked.inspection_id=null;updateInspectionButton();gridControls();
  try{
    const data=await(await request('/api/check',{project:current})).json();
    if(expected!==revision){notice('Inputs changed during checking. Check the current draft.');return;}
    checked={...data,revision:expected,project:current};showDerived(data.derived);renderResults(data.result);drawPreview(data.preview);$('stale').hidden=true;
    $('angle-equivalent').textContent=`≈ ${data.result.pressure_angle_limit_deg_approx.toFixed(3)}° (display only)`;
    $('export').disabled=data.result.status!=='pass';
    announceResult(data.result);
  }catch(error){notice(error.message);$('profile-status').textContent=checked?`Stale · previous ${states[checked.result.status]}`:'Not checked';$('profile-status').className='unknown';if(checked){$('stale').textContent='Check failed · previous result';$('stale').hidden=false;}}finally{checkBusy=false;$('check').disabled=false;$('check').textContent='Check geometry';updateInspectionButton();gridControls();}
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
$('add').addEventListener('click',()=>edit(()=>project.segments.push({span_deg:'30',end_mm:'0'}),{index:project.segments.length,control:'span'}));
$('undo').addEventListener('click',()=>{if(!history.length)return;project=history.pop();focusSnapshot=null;derived=[];changed();renderInputs();$('undo').disabled=!history.length;});
$('save').addEventListener('click',async()=>{const expected=revision;try{const data=await validate();if(expected!==revision){notice('Inputs changed. Save the current draft again.');return;}download(new Blob([JSON.stringify(data.project,null,2)+'\n'],{type:'application/json'}),'camwright-project.json');dirty=false;notice('Project downloaded.');}catch(error){notice(error.message);}});
$('open').addEventListener('click',()=>{$('file').value='';$('file').click();});
$('file').addEventListener('change',async()=>{
  const file=$('file').files[0];if(!file)return;if(file.size>32768){notice('Project exceeds 32 KiB. Current inputs are retained.');return;}
  const expected=revision;try{const text=await file.text(),data=await validate('{"project":'+text+'}');if(expected!==revision){notice('Inputs changed while opening. Select the file again.');return;}replaceProject(data.project,data.derived,true);notice('Project opened. Check geometry to update the profile.');}catch(error){notice(error.message);}
});
$('example').addEventListener('click',async()=>{if(dirty&&!confirm('Replace the current draft with the example? Save project first to keep it.'))return;const expected=revision;try{const data=await(await request('/api/example')).json();const valid=await(await request('/api/validate',{project:data.project??data})).json();if(expected!==revision){notice('Inputs changed while loading the example. Current draft retained.');return;}replaceProject(valid.project,valid.derived,true);notice('Example loaded.');}catch(error){notice(error.message);}});
$('inspection').addEventListener('click',async()=>{
  if(inspectionBusy||checkBusy||exportBusy||!!gridOperation||!checked?.inspection_id||checked.revision!==revision)return;
  const expected=revision,receipt=checked.inspection_id,current=copy(project),projectId=checked.project_id;
  inspectionBusy=true;updateInspectionButton();$('inspection').textContent='Saving inspection…';notice('');
  try{
    const response=await request('/api/inspection',{project:current,project_id:projectId,inspection_id:receipt});
    const blob=await response.blob();
    if(expected!==revision||receipt!==checked?.inspection_id||checkBusy){notice('Inputs or check changed while saving. Save the current completed inspection again.');return;}
    download(blob,'camwright-inspection.zip');notice('Inspection downloaded. Open inspection.html from the ZIP to read the saved observation offline.');
  }catch(error){if(expected===revision&&receipt===checked?.inspection_id)notice(error.message);}
  finally{inspectionBusy=false;$('inspection').textContent='Save inspection';updateInspectionButton();}
});
$('export').addEventListener('click',async()=>{
  if(gridOperation||exportBusy||!checked||checked.revision!==revision||checked.result.status!=='pass')return;
  exportBusy=true;gridControls();const expected=revision;$('export').disabled=true;$('export').textContent='Bounding export…';$('export-status').hidden=true;notice('');
  try{const response=await request('/api/export',{project:copy(project),project_id:checked.project_id});const blob=await response.blob();if(expected!==revision){notice('Inputs changed during export. No file downloaded. Check the current draft.');return;}download(blob,'camwright-profile.zip');$('export-status').textContent=`Export Pass · ${response.headers.get('X-Camwright-Vertices')} vertices · CAD ${response.headers.get('X-Camwright-CAD-Status')||'not reported'} · physical bound ${response.headers.get('X-Camwright-Cam-Bound-Mm')} mm · pitch bound ${response.headers.get('X-Camwright-Pitch-Bound-Mm')} mm. ZIP includes exact project and certificates.`;$('export-status').hidden=false;}catch(error){notice(error.message);$('export-status').textContent=`Export ${states[error.data?.status]||'refused'} · no geometry downloaded.`;$('export-status').hidden=false;}finally{exportBusy=false;gridControls();$('export').textContent='Export profile ZIP';$('export').disabled=!checked||checked.revision!==revision||checked.result.status!=='pass';}
});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
document.querySelectorAll('.inputs input,.inputs button,#save,#undo,#example').forEach(e=>e.disabled=true);
function gridKey() {
  return JSON.stringify([project,$('grid-bases').value,$('grid-rollers').value,$('grid-budget').value]);
}
function gridFresh() {
  return !!gridReport && gridReportRevision===revision && gridReportEpoch===gridEpoch && gridReportKey===gridKey();
}
function gridControls() {
  const busy=!!gridOperation||checkBusy||exportBusy;
  $('check').disabled=busy||!project;
  $('export').disabled=busy||!checked||checked.revision!==revision||checked.result.status!=='pass';
  $('grid-explore').disabled=busy||!project;
  $('grid-use').disabled=busy||!gridFresh()||!gridReport.selection;
  $('grid-save').disabled=!!gridOperation||!gridReport;
  $('grid-cancel').hidden=!gridOperation;
  $('grid-cancel').disabled=!gridOperation||gridOperation.cancelRequested;
  for(const button of $('grid-rows').querySelectorAll('button'))button.disabled=busy||!gridFresh();
}
function invalidateGrid() {
  if(gridReport||gridOperation){
    $('grid-context').hidden=false;
    $('grid-context').textContent='Inputs changed. Any grid below belongs to the earlier motion, limits or radius lists.';
    if(gridOperation)$('grid-status').textContent='Inputs changed while calculating. Waiting for earlier work to finish; no result will replace this draft.';
  }
  gridControls();
}
function gridFocusOwner(button) {
  const owned=document.activeElement===button;
  let moved=false;
  const activity=()=>{moved=true;};
  const focus=event=>{if(event.target!==button&&event.target!==document.body)moved=true;};
  document.addEventListener?.('pointerdown',activity,true);
  document.addEventListener?.('keydown',activity,true);
  document.addEventListener?.('focusin',focus,true);
  return target=>{
    document.removeEventListener?.('pointerdown',activity,true);
    document.removeEventListener?.('keydown',activity,true);
    document.removeEventListener?.('focusin',focus,true);
    if(target&&owned&&!moved&&document.hasFocus?.()&&[button,document.body].includes(document.activeElement))target.focus();
  };
}
function currentGridOperation(op) {
  return gridOperation===op&&op.revision===revision&&op.epoch===gridEpoch&&op.key===gridKey();
}
function beginGridOperation(button,kind) {
  if(gridOperation||checkBusy||exportBusy||!project)return null;
  const op={kind,revision,epoch:gridEpoch,key:gridKey(),source:copy(project),projectId:null,started:false,cancelRequested:false,cancelAccepted:false,finishFocus:gridFocusOwner(button)};
  if(kind==='explore'&&gridReport){gridReportEpoch=-1;$('grid-context').hidden=false;$('grid-context').textContent='The previous grid is retained while a new calculation runs.';}
  gridOperation=op;$('check').disabled=true;$('export').disabled=true;updateInspectionButton();gridControls();
  return op;
}
function endGridOperation(op,target) {
  if(gridOperation!==op){op.finishFocus(null);return;}
  if(!currentGridOperation(op))$('grid-status').textContent='Earlier calculation finished. No result was applied to the edited inputs.';
  gridOperation=null;
  if(gridReport&&!gridFresh()){
    $('grid-context').hidden=false;
    $('grid-context').textContent='The previous grid is retained for reference. Explore the current inputs again before using a pair.';
  }
  $('check').disabled=checkBusy;
  $('export').disabled=exportBusy||!checked||checked.revision!==revision||checked.result.status!=='pass';
  updateInspectionButton();gridControls();op.finishFocus(target);
}
function renderGrid(report) {
  $('grid-result').hidden=false;$('grid-rows').replaceChildren();
  $('grid-summary').textContent=report.minimum_within_grid?'Minimum within this fully classified grid':report.selection?'Passing pair found · minimum not established':report.outcome==='no_pass_in_grid'?'No Pass in this grid':'No passing pair established';
  const unresolved=report.candidates.filter(row=>row.status==='unknown').length;
  $('grid-progress').textContent=`${report.evaluated} of ${report.total} pairs checked · ${report.status==='unfinished'?'Unfinished':'Complete'} · ${unresolved} unresolved. Only this declared grid and supported geometric model were inspected.`;
  for(const row of report.candidates){
    const action=element('td');
    if(row.status==='pass'){
      const button=element('button',{'aria-label':`Use base ${row.base_radius} mm and roller ${row.roller_radius} mm`},'Use pair');
      button.addEventListener('click',()=>useGridPair(row,button));action.append(button);
    }else action.textContent='Fresh Pass required';
    $('grid-rows').append(element('tr',{},element('td',{},row.base_radius),element('td',{},row.roller_radius),element('td',{},row.zero_lift_pitch_radius_mm_exact),element('td',{class:row.status},states[row.status]||'Unresolved'),action));
  }
  gridControls();
}
async function exploreGrid() {
  const op=beginGridOperation($('grid-explore'),'explore');if(!op)return;
  let target=null;
  $('grid-status').textContent='Validating the current source, then checking the finite radius grid…';
  try{
    const options={base_radii:$('grid-bases').value.split(',').map(x=>x.trim()),roller_radii:$('grid-rollers').value.split(',').map(x=>x.trim()),max_candidates:Number($('grid-budget').value)};
    const valid=await(await request('/api/validate',{project:op.source})).json();op.projectId=valid.project_id;
    if(!currentGridOperation(op))return;
    if(op.cancelRequested){$('grid-status').textContent='Stopped before a calculation was started.';target=$('grid-explore');return;}
    op.started=true;
    const report=await(await request('/api/explore',{project:op.source,options})).json();
    if(!currentGridOperation(op))return;
    if(op.cancelRequested){$('grid-status').textContent='The request finished after Stop was requested. No result was applied.';target=$('grid-explore');return;}
    if(!Array.isArray(report.candidates)||report.request?.source_project_id!==op.projectId)throw new Error('The grid result does not match its source. Try again.');
    gridReport=report;gridReportRevision=revision;gridReportEpoch=gridEpoch;gridReportKey=op.key;
    $('grid-context').hidden=false;$('grid-context').textContent='Grid matches the current motion, limits and radius lists. Each Use action runs a fresh geometric check.';
    renderGrid(report);$('grid-status').textContent=`Grid check ${report.status==='unfinished'?'unfinished':'complete'}. ${report.evaluated} of ${report.total} pairs checked.`;
    target=$('grid-summary');
  }catch(error){
    if(currentGridOperation(op)){
      $('grid-status').textContent=op.cancelRequested&&error.data?.error?.code==='cancelled'?'Calculation cancelled by the server. No result applied.':error.message;
      target=op.cancelRequested?$('grid-explore'):null;
    }
  }finally{endGridOperation(op,target);}
}
async function useGridPair(row,button) {
  if(!gridFresh()||row.status!=='pass')return;
  const op=beginGridOperation(button,'select');if(!op)return;
  op.projectId=gridReport.request.source_project_id;let target=null;
  $('grid-status').textContent='Freshly checking this radius pair before applying it…';
  try{
    op.started=true;
    const req=gridReport.request;
    const data=await(await request('/api/select',{project:op.source,project_id:op.projectId,options:{base_radii:req.base_radii,roller_radii:req.roller_radii,request_id:req.request_id,base_index:row.base_index,roller_index:row.roller_index}})).json();
    if(!currentGridOperation(op))return;
    if(op.cancelRequested){$('grid-status').textContent='The selection finished after Stop was requested. The draft was retained.';target=$('grid-explore');return;}
    if(data.status!=='pass'||data.selection_rechecked!==true)throw new Error('A fresh geometric Pass is required before applying a pair.');
    const valid=await(await request('/api/validate',{project:data.project})).json();
    if(!currentGridOperation(op))return;
    if(op.cancelRequested){$('grid-status').textContent='Selection stopped. The draft was retained.';target=$('grid-explore');return;}
    replaceProject(valid.project,valid.derived);op.revision=revision;op.key=gridKey();
    $('grid-status').textContent='Freshly rechecked pair applied to the editor. Run Check geometry for its profile, inspection and export.';
    target=$('check');
  }catch(error){if(currentGridOperation(op))$('grid-status').textContent=op.cancelRequested&&error.data?.error?.code==='cancelled'?'Calculation cancelled by the server. The draft was retained.':error.message;}
  finally{endGridOperation(op,target);}
}
async function stopGrid() {
  const op=gridOperation;if(!op||op.cancelRequested)return;
  op.finishFocus(null);op.finishFocus=gridFocusOwner($('grid-cancel'));op.cancelRequested=true;gridControls();
  if(!op.started){$('grid-status').textContent='Stopping before calculation starts…';return;}
  $('grid-status').textContent='Requesting cancellation of this source’s active calculation…';
  try{
    const data=await(await request('/api/cancel',{project_id:op.projectId})).json();
    if(!currentGridOperation(op))return;
    op.cancelAccepted=data.cancelled===true;
    $('grid-status').textContent=op.cancelAccepted?'Stop accepted. Waiting for the calculation response.':'No matching active calculation was stopped. Waiting for the request to finish.';
  }catch(error){if(currentGridOperation(op))$('grid-status').textContent=`Stop could not be confirmed: ${error.message} Waiting for the calculation response.`;}
}
$('grid-bases').value||= '20,25,30';$('grid-rollers').value||='4,5,6';$('grid-budget').value||='64';
for(const id of ['grid-bases','grid-rollers','grid-budget'])$(id).addEventListener('input',()=>{gridEpoch++;invalidateGrid();});
$('grid-explore').addEventListener('click',exploreGrid);
$('grid-cancel').addEventListener('click',stopGrid);
$('grid-use').addEventListener('click',async()=>{if(!gridFresh()||!gridReport.selection)return;const row=gridReport.candidates.find(x=>x.base_index===gridReport.selection.base_index&&x.roller_index===gridReport.selection.roller_index);if(row)await useGridPair(row,$('grid-use'));});
$('grid-save').addEventListener('click',()=>{if(gridReport&&!gridOperation)download(new Blob([JSON.stringify(gridReport,null,2)+'\n'],{type:'application/json'}),'camwright-grid.json');});
(async()=>{try{const data=await(await request('/api/example')).json();const valid=await(await request('/api/validate',{project:data.project??data})).json();replaceProject(valid.project,valid.derived,true);$('check').click();}catch(error){notice(error.message);$('check').disabled=true;$('example').disabled=false;}})();
