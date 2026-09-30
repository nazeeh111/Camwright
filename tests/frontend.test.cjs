const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// No DOM dependency is needed. This harness runs the real frontend and substitutes
// only browser node/focus operations and the HTTP transport. Browser rendering and
// assistive-technology announcements still require the separate runtime review.
function harness(result) {
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
    focus() { if (!this.disabled) document.activeElement = this; }
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
    fetch: async pathname => {
      if (boot) { boot = false; return new Promise(() => {}); }
      if (pathname === '/api/check') return {ok: true, json: async () => structuredClone(data)};
      throw new Error(`Unexpected request ${pathname}`);
    }
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'app.js'), 'utf8'), context);
  context.fixtureProject = project;
  vm.runInContext('replaceProject(fixtureProject, null, true)', context);
  return {document, context, get: id => document.getElementById(id), run: source => vm.runInContext(source, context)};
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
