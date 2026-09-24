// faro web app: boot, login, tabs, live data and the pieces shared by every view.
import { charts } from './chart.js';
import { $, $$, esc, f0, gib, hhmm, rate, store } from './fmt.js';
import { setLanguage, t } from './i18n.js';
import { icon } from './icons.js';
import * as home from './views/home.js';
import * as system from './views/system.js';
import * as services from './views/services.js';
import * as disks from './views/disks.js';
import * as sheet from './views/sheet.js';

const TABS = ['home', 'system', 'services', 'disks'];
const VIEWS = { home, system, services, disks };

// everything the views share
export const app = {
  S: null,            // last full state from /api/state, kept up to date by the stream
  SUM: {},            // summary computed once per update
  tab: 'home',
  lastMsg: 0,
  render,
  toast,
  api,
};

/* ------------------------------------------------------------------ api */

async function api(path, body) {
  const opts = body === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Faro': '1' }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  if (r.status === 401) { showLogin(); throw new Error('login required'); }
  return r.json();
}

/* ------------------------------------------------------------------ theme and wallpaper */

// four palettes for the time of day; the aurora blobs take these colours
const PALETTES = {
  night:     { dark: ['#070a18', '#1d2f7a', '#3b1f6e', '#0b4f5c'], light: ['#e3e7f5', '#b6c3f2', '#d4c1f0', '#b5e1e8'] },
  morning:   { dark: ['#0a1326', '#2b62d9', '#a8582a', '#128a87'], light: ['#eef3fb', '#a9c8ff', '#ffd2a8', '#a8efe4'] },
  afternoon: { dark: ['#0b0f20', '#2d4fc0', '#7a2ea8', '#0e7b73'], light: ['#e7ecf7', '#9dbcff', '#f1b5dd', '#a3e9d4'] },
  evening:   { dark: ['#080a1a', '#352a9a', '#8f2464', '#145a86'], light: ['#e6e6f5', '#b3b0f5', '#f0b3d4', '#a9d4ee'] },
};
const period = h => h < 7 ? 'night' : h < 13 ? 'morning' : h < 20 ? 'afternoon' : 'evening';

export function isDark() {
  const th = document.documentElement.dataset.theme;
  return th ? th === 'dark' : !matchMedia('(prefers-color-scheme: light)').matches;
}

export function applyTheme(th) {
  if (th) document.documentElement.dataset.theme = th; else delete document.documentElement.dataset.theme;
  paintWall();
  charts.forEach(c => c.draw());
}

function paintWall() {
  const c = PALETTES[period(new Date().getHours())][isDark() ? 'dark' : 'light'];
  const r = document.documentElement;
  ['--wall', '--wb1', '--wb2', '--wb3'].forEach((v, i) => r.style.setProperty(v, c[i]));
  $('#theme-color').content = c[0];
}
setInterval(paintWall, 5 * 60 * 1000);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paintWall);
document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('hidden-tab', document.hidden));

export function applyEffects(on) {
  document.documentElement.classList.toggle('flat', !on);
}

/* ------------------------------------------------------------------ small ui helpers */

let toastTimer = null;
function toast(text, bad) {
  const el = $('#toast');
  el.textContent = text;
  el.className = 'toast on' + (bad ? ' bad' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast' + (bad ? ' bad' : ''); }, 3200);
}

function translateStatic() {
  $$('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  $$('.dock button').forEach(b => { $('.ico', b).innerHTML = icon(b.dataset.i); });
  $$('.bell').forEach(b => { b.innerHTML = icon('campana') + '<i hidden></i>'; b.setAttribute('aria-label', t('alerts')); });
}

/* ------------------------------------------------------------------ tabs */

function showTab(name, push = true) {
  if (!TABS.includes(name)) name = 'home';
  const before = app.tab;
  app.tab = name;
  document.body.dataset.tab = name;
  $$('.pane').forEach(p => p.classList.toggle('on', p.id === 'p-' + name));
  $$('#dock button[data-tab]').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  $('#title').textContent = name === 'home' ? '' : t('tab_' + name);
  if (location.hash.slice(1) !== name) {
    // the phone's back button returns home instead of leaving the app
    if (push && before === 'home' && name !== 'home') history.pushState({ tab: name }, '', '#' + name);
    else history.replaceState(null, '', '#' + name);
  }
  store.set('tab', name);
  if (app.S) render();
  $('#main').scrollTop = 0;
}

$('#dock').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.sheet) sheet.open(b.dataset.sheet);
  else showTab(b.dataset.tab);
});
$('#back').onclick = () => (history.state && history.state.tab ? history.back() : showTab('home'));
addEventListener('popstate', () => showTab(location.hash.slice(1) || 'home', false));
addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey || /input|textarea|select/i.test(e.target.tagName)) return;
  const i = '1234'.indexOf(e.key);
  if (i >= 0) showTab(TABS[i]);
  if (e.key === 'Escape') sheet.close();
});
$$('.bell').forEach(b => b.addEventListener('click', () => sheet.open('alerts')));

/* ------------------------------------------------------------------ summary */

export function pkgTemp(h) {
  const recent = (h.live || []).slice(-5).map(p => p.temp).filter(v => v != null).sort((a, b) => a - b);
  return recent.length ? recent[recent.length >> 1] : h.data?.cpu_temp ?? null;
}

export function diskHealth(x) {
  const sm = x.smart || {};
  if (sm.standby) return ['idle', t('standby')];
  if (sm.healthy === false) return ['crit', t('smart_fail')];
  if (sm.realloc || sm.pending) return ['warn', t('bad_sectors', { n: (sm.realloc || 0) + (sm.pending || 0) })];
  return sm.healthy ? ['good', t('smart_ok')] : ['idle', t('no_smart')];
}

export function guests() {
  const out = {};
  for (const h of app.S.config.hosts) {
    const d = app.S.hosts[h.id]?.data;
    const gc = d?.gcpu || {};
    for (const g of d?.guests || []) {
      // % of the cores the guest has, like Proxmox; the host's cgroup has the real figure
      const cpu = gc[g.vmid] != null && g.cpus ? Math.min(100, 100 * gc[g.vmid] / g.cpus) : g.cpu;
      out[`${h.id}:${g.vmid}`] = { ...g, cpu, host: h.id };
    }
  }
  return out;
}

function summarise() {
  const S = app.S;
  const checked = S.config.services.filter(s => s.check !== 'none' || S.services[s.id]);
  const st = checked.map(s => S.services[s.id] || {});
  const up = st.filter(s => s.up).length, known = st.filter(s => s.up != null).length;
  const gs = Object.values(guests());
  let used = 0, total = 0, rx = 0, tx = 0, hot = null, diskBad = 0, ndisk = 0, cpu = null;
  for (const h of S.config.hosts) {
    const d = S.hosts[h.id]?.data;
    if (!d) continue;
    const pools = d.zfs?.pools || [];
    for (const p of pools) { used += p.alloc; total += p.size; if (p.health !== 'ONLINE') diskBad++; }
    for (const f of d.fs || []) {
      // ZFS datasets are already counted in their pool
      if (f.type === 'zfs' && pools.length) continue;
      if (f.mount === '/' || f.mount.startsWith('/mnt/') || f.mount.startsWith('/srv') || f.mount.startsWith('/data')) {
        used += f.used; total += f.total;
      }
    }
    for (const x of d.disks || []) { ndisk++; if (['crit', 'warn'].includes(diskHealth(x)[0])) diskBad++; }
    const n = d.net?.[h.nic || d.nic] || {};
    rx += n.rx || 0; tx += n.tx || 0;
    const p = pkgTemp(S.hosts[h.id]);
    if (p != null && (!hot || p > hot.v)) hot = { v: p, n: h.name };
    if (d.cpu?.total != null) cpu = Math.max(cpu ?? 0, d.cpu.total);
  }
  const online = S.config.hosts.filter(h => S.hosts[h.id]?.online).length;
  app.SUM = { up, total: checked.length, known, bad: known - up, online, nhosts: S.config.hosts.length,
              running: gs.filter(g => g.status === 'running').length, nguests: gs.length,
              hot, used, size: total, ndisk, diskBad, rx, tx, cpu };
}

function renderSummary() {
  const U = app.SUM;
  $('#dock-svc').hidden = !(U.known && U.bad);
  $('#dock-disk').hidden = !U.diskBad;
  const alerts = (app.S.problems || []).length;
  $$('.bell i').forEach(i => { i.hidden = !alerts; });
  $('#summary').innerHTML = `
    <div><div class="k">${t('sum_services')}</div><div class="v num">${U.up}<small> / ${U.total}</small></div>
      <div class="d"><span class="st ${!U.known ? 'idle' : U.bad ? 'crit' : 'good'}"><i></i>${!U.known ? t('checking_s') : U.bad ? t('n_down', { n: U.bad }) : t('all_responding')}</span></div></div>
    <div><div class="k">${t('sum_hosts')}</div><div class="v num">${U.online}<small> ${t('online_of', { n: U.nhosts })}</small></div>
      <div class="d">${U.nguests ? t('guests_on', { on: U.running, n: U.nguests }) : '&nbsp;'}</div></div>
    <div><div class="k">${t('sum_hottest')}</div><div class="v num">${U.hot ? f0(U.hot.v) : '–'}<small> °C</small></div>
      <div class="d">${U.hot ? esc(t('cpu_of', { name: U.hot.n })) : '&nbsp;'}</div></div>
    <div><div class="k">${t('sum_storage')}</div><div class="v num">${gib(U.used).replace(/ (\S+)$/, '<small> $1</small>')}</div>
      <div class="d">${t('of')} ${gib(U.size)} · ${U.diskBad ? `<span class="crit-t">${t('disks_bad', { n: U.ndisk, bad: U.diskBad })}</span>` : t('disks_ok', { n: U.ndisk })}</div></div>
    <div><div class="k">${t('sum_net')}</div><div class="v num sm"><span class="io"><span class="dn">${rate(U.rx)}</span> &nbsp; <span class="up">${rate(U.tx)}</span></span></div>
      <div class="d">${t('physical_nics')}</div></div>`;
}

/* ------------------------------------------------------------------ render loop */

function render() {
  if (!app.S) return;
  summarise();
  renderSummary();
  VIEWS[app.tab].render(app);
  sheet.refresh(app);
}

function merge(m) {
  const S = app.S;
  S.now = m.now;
  S.problems = m.problems;
  for (const [id, h] of Object.entries(m.hosts)) {
    const cur = S.hosts[id] ||= { live: [], day: [] };
    Object.assign(cur, { data: h.data, error: h.error, online: h.online, last: h.last });
    if (h.last && (!cur.live.length || cur.live[cur.live.length - 1].t !== h.last.t)) {
      cur.live.push(h.last);
      if (cur.live.length > 900) cur.live.shift();
    }
  }
  for (const [id, s] of Object.entries(m.services)) {
    const cur = S.services[id] ||= { history: [] };
    Object.assign(cur, s);
    if (s.last && (!cur.history.length || cur.history[cur.history.length - 1][0] !== s.last[0])) {
      cur.history.push(s.last);
      if (cur.history.length > 90) cur.history.shift();
    }
  }
}

let es = null;
function connect() {
  es?.close();
  es = new EventSource('/api/stream');
  es.onmessage = e => {
    app.lastMsg = Date.now();
    merge(JSON.parse(e.data));
    render();
    setLive(true);
  };
  es.onerror = () => setLive(false);
}

// the 24 h series only changes once a minute: refresh it from the full state
setInterval(async () => {
  if (!app.S || document.hidden) return;
  try {
    const full = await api('/api/state');
    for (const [id, h] of Object.entries(full.hosts)) if (app.S.hosts[id]) app.S.hosts[id].day = h.day;
  } catch (e) { /* the stream will reconnect */ }
}, 60000);

function setLive(on) {
  const el = $('#live');
  el.className = 'live ' + (on ? 'on' : 'off');
  $('span', el).textContent = on ? t('live') : t('offline_conn');
}
setInterval(() => { if (Date.now() - app.lastMsg > 5000) setLive(false); }, 2000);

function tick() {
  const now = Date.now() / 1000;
  $('#clock').textContent = hhmm(now);
  home.clock(app);
}
setInterval(tick, 1000);

/* ------------------------------------------------------------------ boot and login */

function showLogin(title) {
  es?.close();
  $('#boot').hidden = true;
  ['#top', '#summary', '#main', '#dock'].forEach(s => { $(s).hidden = true; });
  if (title) $('#login-title').textContent = title;
  $('#login').hidden = false;
  $('#login-pw').focus();
}

$('#login').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#login button');
  btn.disabled = true;
  $('#login-err').textContent = '';
  try {
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Faro': '1' },
                                          body: JSON.stringify({ password: $('#login-pw').value }) });
    if (r.ok) { $('#login').hidden = true; $('#login-pw').value = ''; await start(); return; }
    $('#login-err').textContent = r.status === 429 ? t('too_many') : t('wrong_password');
  } finally { btn.disabled = false; }
});

export async function logout() {
  await api('/api/logout', {});
  location.reload();
}

async function start() {
  const S = await api('/api/state');
  app.S = S;
  document.title = S.config.title;
  $('#boot').hidden = true;
  ['#top', '#summary', '#main', '#dock'].forEach(s => { $(s).hidden = false; });
  for (const v of Object.values(VIEWS)) v.build?.(app);
  showTab(location.hash.slice(1) || store.get('tab') || 'home', false);
  connect();
}

async function boot() {
  let me;
  try {
    me = await (await fetch('/api/me', { cache: 'no-store' })).json();
  } catch (e) {
    $('#boot p').textContent = t('no_connection');
    setTimeout(boot, 3000);
    return;
  }
  setLanguage(me.language);
  translateStatic();
  applyTheme(store.get('theme'));
  applyEffects(store.get('effects') !== false);
  $('#login-title').textContent = me.title;
  if (me.auth && !me.logged_in) return showLogin(me.title);
  await start();
}

paintWall();
boot();

if ('serviceWorker' in navigator && location.protocol === 'https:') {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

export { showTab, translateStatic };
