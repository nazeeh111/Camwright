const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// No DOM dependency is needed. This harness runs the real frontend and substitutes
// only browser node/focus operations and the HTTP transport. Browser rendering and
// assistive-technology announcements still require the separate runtime review.
function harness(result, hooks = {}) {
  let document;
  class Node {
    constructor(tag = '#text', text = '') {
      this.tagName = tag; this.text = text; this.children = []; this.attributes = {};
      this.listeners = {}; this.disabled = false; this.hidden = false; this.className = '';
      this.classList = {toggle: (name, force) => {
        const names = new Set(this.className.split(/\s+/).filter(Boolean));
        force ? names.add(name) : names.delete(name); this.className = [...names].join(' ');
      }};
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name] ?? null; }
    append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
    contains(node) { return this === node || this.children.some(child => child.contains(node)); }
    replaceChildren(...children) {
      if (this.children.some(child => child.contains(document.activeElement))) document.activeElement = document.body;
      this.children = []; this.text = ''; this.append(...children);
    }
    set textContent(text) { this.replaceChildren(); this.text = String(text); }
    get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
    get firstChild() { return this.children[0]; }
    addEventListener(type, listener) { (this.listeners[type] ??= []).push(listener); }
    async click() {
      if (this.disabled) return;
      if (this.onclick) await this.onclick({currentTarget: this});
      for (const listener of this.listeners.click ?? []) await listener({currentTarget: this});
    }
    focus() { if (!this.disabled) { document.activeElement = this; document.dispatchEvent({type:'focusin',target:this}); } }
    async emit(type) { for(const listener of this.listeners[type]??[])await listener({target:this}); }
    scrollIntoView(options) { this.scrollOptions = options; }
    remove() { this.parent.children = this.parent.children.filter(node => node !== this); }
    matches(selector) {
      if (selector.startsWith('.')) return this.className.split(/\s+/).includes(selector.slice(1));
      if (selector.startsWith('#')) return this.getAttribute('id') === selector.slice(1);
      const attribute = selector.match(/^\[([^=]+)="([^"]+)"\]$/);
      if (attribute) return this.getAttribute(attribute[1]) === attribute[2];
      return this.tagName === selector;
    }
    querySelectorAll(selector) {
      const selectors = selector.split(',').map(value => value.trim()), found = [];
      for (const child of this.children) {
        if (selectors.some(value => child.matches(value))) found.push(child);
        found.push(...child.querySelectorAll(selector));
      }
      return found;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
  }
  document = {
    body: new Node('body'), createElement: tag => new Node(tag),
    createElementNS: (_namespace, tag) => new Node(tag), createTextNode: text => new Node('#text', text),
    getElementById(id) { return this.body.querySelector(`#${id}`); },
    querySelectorAll(selector) { return this.body.querySelectorAll(selector); }
  };
  const documentListeners={};
  document.addEventListener=(type,fn)=>{(documentListeners[type]??=[]).push(fn);};
  document.removeEventListener=(type,fn)=>{documentListeners[type]=(documentListeners[type]??[]).filter(x=>x!==fn);};
  document.dispatchEvent=event=>{for(const fn of [...(documentListeners[event.type]??[])])fn(event);};
  document.hasFocus=()=>hooks.active!==false;
  document.activeElement = document.body;
  const directory = path.join(__dirname, '..', 'camwright', 'static');
  const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
  for (const match of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const node = new Node(match[1]);
    for (const attr of match[0].matchAll(/([\w-]+)="([^"]*)"/g)) node.setAttribute(attr[1], attr[2]);
    node.disabled = /\sdisabled[\s>]/.test(match[0]);
    document.body.append(node);
  }
  const project = JSON.parse(fs.readFileSync(path.join(directory, '..', 'examples', 'accepted.json'), 'utf8'));
  const data = {
    result, project_id: 'project', inspection_id: 'inspection',
    derived: {total_deg_exact: '360', remaining_deg_exact: '0', segments: [
      {start_deg_exact: '0', end_deg_exact: '120', end_mm_exact: '20', motion: 'rise'},
      {start_deg_exact: '120', end_deg_exact: '180', end_mm_exact: '20', motion: 'dwell'},
      {start_deg_exact: '180', end_deg_exact: '300', end_mm_exact: '0', motion: 'return'},
      {start_deg_exact: '300', end_deg_exact: '360', end_mm_exact: '0', motion: 'dwell'}
    ]},
    preview: {points: [
      {angle_deg: 0, cam: [60, 0], pitch: [65, 0], lift_mm: 0},
      {angle_deg: 180, cam: [-80, 0], pitch: [-85, 0], lift_mm: 20}
    ]}
  };
  let boot = true;
  const context = vm.createContext({document, Node, structuredClone,
    window: {addEventListener() {}, matchMedia: () => ({matches: true})},
    setTimeout: () => 1, clearTimeout() {}, confirm: () => true,
    fetch: async (pathname, options) => {
      if (boot) { boot = false; return new Promise(() => {}); }
      if(hooks.request){const value=await hooks.request(pathname,options?.body?JSON.parse(options.body):undefined);if(value!==undefined)return value.ok!==undefined?value:{ok:true,json:async()=>structuredClone(value)};}
      if (pathname === '/api/check') return {ok: true, json: async () => structuredClone(data)};
      throw new Error(`Unexpected request ${pathname}`);
    }
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'app.js'), 'utf8'), context);
  context.fixtureProject = project;
  vm.runInContext('replaceProject(fixtureProject, null, true)', context);
  return {document, context, documentListeners, get: id => document.getElementById(id), run: source => vm.runInContext(source, context)};
}

function result(status = 'pass') {
  return {status, pressure_angle_limit_deg_approx: 26.565, segments: [0, 1, 2, 3].map(segment => ({
    segment, checks: {
      pressure: status === 'fail' && segment === 0
        ? {status: 'fail', boxes: 1, angle_deg: '60', value: ['-10', '-5']}
        : {status: 'pass', boxes: 5, leaves: [['0', '1']]},
      convex_pitch: status === 'unknown' && segment === 2
        ? {status: 'unknown', boxes: 7, angle_interval_deg: ['210', '240'], reason: 'work_or_depth_limit'}
        : {status: 'pass', boxes: 3, leaves: [['0', '1']]},
      roller_curvature: {status: 'pass', boxes: 1, leaves: [['0', '1']]}
    }
  }))};
}

test('completed checks announce the result and preserve fresh/stale export gates', async () => {
  for (const status of ['pass', 'fail', 'unknown']) {
    const app = harness(result(status));
    await app.get('check').click();
    const announcement = app.get('check-announcement');
    assert.ok(announcement, 'a stable completed-result live region exists');
    assert.equal(announcement.getAttribute('role'), 'status');
    assert.match(announcement.textContent, new RegExp(status === 'unknown' ? 'Unresolved' : status === 'pass' ? 'Pass' : 'Fail'));
    assert.equal(app.get('export').disabled, status !== 'pass');
    assert.equal(app.get('inspection').disabled, false);
    app.run('changed()');
    assert.equal(app.get('export').disabled, true);
    assert.equal(app.get('inspection').disabled, true);
    assert.match(app.get('profile-status').textContent, /Stale/);
  }
});

test('reorder, removal and addition keep focus in the affected segment', async () => {
  const app = harness(result());
  let control = app.get('segments').children[0].querySelectorAll('button')[1];
  control.focus(); await control.click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Move segment down: segment 2');
  assert.equal(app.document.activeElement, app.get('segments').children[1].querySelectorAll('button')[1]);
  await app.document.activeElement.click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Move segment down: segment 3');
  control = app.get('segments').children[2].querySelectorAll('button')[2];
  control.focus(); await control.click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Remove segment 3');
  await app.document.activeElement.click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Remove segment 2');
  await app.document.activeElement.click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Segment 1 span in degrees');
  await app.get('add').click();
  assert.equal(app.document.activeElement.getAttribute('aria-label'), 'Segment 2 span in degrees');
});

test('all witness actions identify check and segment, navigate alike, and reject stale results', async () => {
  const app = harness(result('fail'));
  await app.get('check').click();
  const card = app.get('check-details').querySelector('button');
  const top = app.get('profile-witness');
  assert.match(card.getAttribute('aria-label') ?? card.textContent, /Pressure limit.*segment 1.*60/i);
  assert.equal(card.getAttribute('aria-label'), top.getAttribute('aria-label'));
  for (const button of [card, top]) {
    await button.click();
    assert.equal(Number(app.get('cursor').value), 60);
    assert.equal(app.document.activeElement, app.get('cursor'));
    assert.equal(app.get('drawing-heading').scrollOptions.behavior, 'auto');
  }
  app.run('changed()');
  app.document.activeElement = app.document.body;
  await card.click();
  assert.equal(app.document.activeElement, app.document.body);
});

test('segment results retain every status, witness and subdivision count', async () => {
  const app = harness(result('unknown'));
  await app.get('check').click();
  const mainTable = app.get('check-details').querySelector('table');
  assert.ok(mainTable, 'results are grouped by segment in a table');
  const rows = mainTable.querySelectorAll('tbody')[0].children;
  assert.equal(rows.length, 4);
  assert.match(rows[2].textContent, /Segment 3.*Unresolved.*210.*240.*Subdivision work or depth limit reached/);
  assert.equal(rows[2].querySelectorAll('strong').filter(node => node.textContent === 'Pass').length, 2);
  const evidence = app.get('check-details').querySelector('details');
  assert.ok(evidence, 'successful check evidence stays available without dominating the summary');
  assert.equal(evidence.querySelectorAll('tbody')[0].children.length, 4);
  assert.match(evidence.textContent, /7/);
});

const deferred = () => { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; };
const flush = async () => { for(let i=0;i<12;i++)await Promise.resolve(); };
function gridFixture(statuses=['fail','pass'], minimum=true, unfinished=false) {
  return {schema:'camwright.sizing-result',version:1,status:unfinished?'unfinished':'complete',outcome:statuses.includes('pass')?'passing_candidate':statuses.includes('unknown')||unfinished?'unknown':'no_pass_in_grid',minimum_within_grid:minimum,
    request:{source_project_id:'source',request_id:'request',base_radii:['20','25','30'],roller_radii:['4','5','6']},
    evaluated:statuses.length,total:9,selection:statuses.includes('pass')?{base_index:statuses.indexOf('pass'),roller_index:0}:null,
    candidates:statuses.map((status,i)=>({base_index:i,roller_index:0,base_radius:String(20+i*5),roller_radius:'4',zero_lift_pitch_radius_mm_exact:String(24+i*5),status}))};
}
function gridHarness(handler, options={}) {
  const calls=[];
  const app=harness(result(),{...options,request:async(path,body)=>{
    calls.push({path,body});
    const custom=await handler?.(path,body);if(custom!==undefined)return custom;
    if(path==='/api/validate')return {project:body.project,project_id:'source',derived:{segments:[]}};
    if(path==='/api/explore')return gridFixture();
    if(path==='/api/select')return {status:'pass',selection_rechecked:true,project:{...body.project,base_radius:'25',roller_radius:'4'}};
    if(path==='/api/cancel')return {cancelled:true};
  }});
  return {...app,calls};
}

test('finite grid selection sends only source/grid identities and requires the normal fresh-check lifecycle', async()=>{
  const app=gridHarness();await app.get('grid-explore').click();
  const explore=app.calls.find(x=>x.path==='/api/explore');
  assert.deepEqual(explore.body.options,{base_radii:['20','25','30'],roller_radii:['4','5','6'],max_candidates:64});
  assert.equal(app.get('grid-use').disabled,false);
  await app.get('grid-use').click();
  const selected=app.calls.find(x=>x.path==='/api/select').body;
  assert.equal(selected.project_id,'source');assert.equal(selected.options.request_id,'request');
  assert.equal(selected.options.base_index,1);assert.equal(selected.options.roller_index,0);
  assert.equal(app.run('project.base_radius'),'25');assert.equal(app.run('project.roller_radius'),'4');
  assert.equal(app.run('checked'),null);assert.equal(app.get('export').disabled,true);assert.equal(app.get('inspection').disabled,true);
  assert.equal(app.get('grid-use').disabled,true);assert.equal(app.get('check').disabled,false);
});

test('late grid success and late error cannot replace edited inputs or surface obsolete errors',async()=>{
  for(const failure of [false,true]){
    const pending=deferred();const app=gridHarness(path=>path==='/api/explore'?pending.promise:undefined);
    const task=app.get('grid-explore').click();await flush();
    app.get('base').value='31';await app.get('base').emit('input');
    const status=app.get('grid-status').textContent;
    failure?pending.reject(new Error('old-request-error')):pending.resolve(gridFixture());await task;
    assert.equal(app.run('project.base_radius'),'31');assert.equal(app.run('gridReport'),null);
    assert.doesNotMatch(app.get('grid-status').textContent,/old-request-error|Waiting/);assert.equal(app.get('grid-explore').disabled,false);
  }
});

test('changing and restoring a radius list still invalidates the earlier request',async()=>{
  const pending=deferred();const app=gridHarness(path=>path==='/api/explore'?pending.promise:undefined);
  const task=app.get('grid-explore').click();await flush();
  const field=app.get('grid-bases'),old=field.value;field.value='30';await field.emit('input');field.value=old;await field.emit('input');
  pending.resolve(gridFixture());await task;
  assert.equal(app.run('gridReport'),null);assert.equal(app.get('grid-use').disabled,true);
});

test('double activation submits one calculation and a refusal allows retry without input loss',async()=>{
  const pending=deferred();let attempts=0;
  const app=gridHarness(path=>path==='/api/explore'?(++attempts===1?pending.promise:gridFixture()):undefined);
  const task=app.get('grid-explore').click();await flush();await app.get('grid-explore').click();
  assert.equal(app.calls.filter(x=>x.path==='/api/explore').length,1);
  pending.resolve({ok:false,json:async()=>({error:{code:'busy',message:'Another worker is active'}})});await task;
  assert.equal(app.run('project.base_radius'),'25');assert.equal(app.get('grid-explore').disabled,false);
  await app.get('grid-explore').click();assert.equal(attempts,2);assert.equal(app.get('grid-use').disabled,false);
});

test('unresolved and unfinished grids retain native outcomes without inventing a minimum or a selection',async()=>{
  for(const report of [gridFixture(['unknown','pass'],false),gridFixture(['fail'],false,true)]){
    const app=gridHarness(path=>path==='/api/explore'?report:undefined);await app.get('grid-explore').click();
    assert.equal(app.run('gridReport.minimum_within_grid'),false);
    assert.equal(app.get('grid-use').disabled,!report.selection);assert.equal(app.get('grid-save').disabled,false);
    assert.doesNotMatch(app.get('grid-summary').textContent,/Minimum within this fully/);
    if(report.selection)assert.match(app.get('grid-rows').textContent,/Unresolved/);
    else assert.equal(app.get('grid-rows').children.length,1);
  }
});

test('accepted cancellation waits for the actual calculation response and sends the captured source identity',async()=>{
  const pending=deferred();const app=gridHarness(path=>path==='/api/explore'?pending.promise:undefined);
  app.get('grid-explore').focus();const task=app.get('grid-explore').click();await flush();
  app.get('grid-cancel').focus();await app.get('grid-cancel').click();
  assert.equal(app.calls.find(x=>x.path==='/api/cancel').body.project_id,'source');
  assert.ok(app.run('gridOperation'));assert.equal(app.get('grid-explore').disabled,true);
  pending.resolve({ok:false,json:async()=>({error:{code:'cancelled',message:'Calculation was cancelled'}})});await task;
  assert.equal(app.run('gridReport'),null);assert.equal(app.run('gridOperation'),null);
  assert.equal(app.document.activeElement,app.get('grid-explore'));
});

test('unconfirmed cancellation never claims server cancellation and ignores the later successful result',async()=>{
  const pending=deferred();const app=gridHarness(path=>path==='/api/explore'?pending.promise:path==='/api/cancel'?{cancelled:false}:undefined);
  const task=app.get('grid-explore').click();await flush();await app.get('grid-cancel').click();
  assert.ok(app.run('gridOperation'));pending.resolve(gridFixture());await task;
  assert.equal(app.run('gridReport'),null);assert.doesNotMatch(app.get('grid-status').textContent,/cancelled by the server/);
  assert.equal(app.run('project.roller_radius'),'5');
});

test('completion focus is owned, respects manual/background/inactive activity and removes listeners',async()=>{
  for(const mode of ['owned','manual','background','inactive']){
    const pending=deferred();const app=gridHarness(path=>path==='/api/explore'?pending.promise:undefined,{active:mode!=='inactive'});
    app.get('grid-explore').focus();const task=app.get('grid-explore').click();await flush();
    if(mode==='manual')app.get('base').focus();
    if(mode==='background')app.document.dispatchEvent({type:'pointerdown',target:app.document.body});
    pending.resolve(gridFixture());await task;
    assert.equal(app.document.activeElement,app.get(mode==='owned'?'grid-summary':mode==='manual'?'base':'grid-explore'));
    assert.equal(Object.values(app.documentListeners).flat().length,0);
  }
});

test('a late selection or selection error cannot apply over a newer project edit',async()=>{
  for(const failure of [false,true]){
    const pending=deferred();const app=gridHarness(path=>path==='/api/select'?pending.promise:undefined);
    await app.get('grid-explore').click();const task=app.get('grid-use').click();await flush();
    app.get('roller').value='6';await app.get('roller').emit('input');const status=app.get('grid-status').textContent;
    failure?pending.reject(new Error('old-selection-error')):pending.resolve({status:'pass',selection_rechecked:true,project:{...app.run('project'),roller_radius:'4'}});
    await task;assert.equal(app.run('project.roller_radius'),'6');assert.doesNotMatch(app.get('grid-status').textContent,/old-selection-error|Waiting/);
    assert.equal(app.get('export').disabled,true);assert.equal(app.get('grid-use').disabled,true);
  }
});

test('a late cancellation error cannot overwrite a newer grid operation',async()=>{
  const first=deferred(),second=deferred(),cancel=deferred();let count=0;
  const app=gridHarness(path=>path==='/api/explore'?(++count===1?first.promise:second.promise):path==='/api/cancel'?cancel.promise:undefined);
  const old=app.get('grid-explore').click();await flush();const stopping=app.get('grid-cancel').click();await flush();
  first.resolve(gridFixture());await old;const fresh=app.get('grid-explore').click();await flush();const status=app.get('grid-status').textContent;
  cancel.reject(new Error('old-cancel-error'));await stopping;assert.equal(app.get('grid-status').textContent,status);
  second.resolve(gridFixture());await fresh;assert.ok(app.run('gridReport'));
});
