// Home: clock and status widget, the app grid and plugin cards.
import { $, esc, f0 } from '../fmt.js';
import { locale, t } from '../i18n.js';
import { appIcon, icon } from '../icons.js';
import { pkgTemp, showTab } from '../main.js';
import * as sheet from './sheet.js';

const cache = {};
let appEls = {};

export function build(app) {
  const svcs = app.S.config.services;
  $('#apps').innerHTML = svcs.map((s, i) => `
    <a class="app wait" style="--i:${i}" data-s="${esc(s.id)}" ${s.url ? `href="${esc(s.url)}" target="_blank" rel="noopener"` : 'role="button" tabindex="0"'}
       title="${esc(s.name)}${s.description ? ' · ' + esc(s.description) : ''}">
      <span class="icw">${appIcon(s)}<i class="badge" hidden>!</i></span>
      <em>${esc(s.name)}</em>
    </a>`).join('');
  appEls = {};
  for (const el of $('#apps').children) appEls[el.dataset.s] = el;
  longPress($('#apps'), id => sheet.open('app', id));
  $('#hostcards').onclick = () => showTab('system');
  loadCards(app);
}

// long press (or right click) on an app opens its details instead of the link
function longPress(root, fn) {
  let timer = null, fired = false;
  root.addEventListener('pointerdown', e => {
    const a = e.target.closest('.app');
    if (!a) return;
    fired = false;
    timer = setTimeout(() => { fired = true; navigator.vibrate?.(10); fn(a.dataset.s); }, 550);
  });
  const cancel = () => clearTimeout(timer);
  root.addEventListener('pointerup', cancel);
  root.addEventListener('pointerleave', cancel);
  root.addEventListener('pointercancel', cancel);
  root.addEventListener('click', e => {
    const a = e.target.closest('.app');
    if (!a) return;
    if (fired || !a.getAttribute('href')) { e.preventDefault(); if (!fired) fn(a.dataset.s); }
  });
  root.addEventListener('contextmenu', e => {
    const a = e.target.closest('.app');
    if (a) { e.preventDefault(); fn(a.dataset.s); }
  });
}

function ring(frac, color, center, label) {
  const r = 23, c = 2 * Math.PI * r, f = Math.max(0, Math.min(1, frac || 0));
  return `<div class="ring"><svg viewBox="0 0 54 54"><circle class="bg" cx="27" cy="27" r="${r}"/>` +
    `<circle class="fg" cx="27" cy="27" r="${r}" style="stroke:${color};stroke-dasharray:${(f * c).toFixed(1)} ${c.toFixed(1)}"/></svg>` +
    `<b>${center}</b><span>${label}</span></div>`;
}

export function clock() {
  const d = new Date();
  const hm = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
  if (cache.hm === hm) return;
  cache.hm = hm;
  $('#w-time').textContent = hm;
  const f = d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' });
  $('#w-date').textContent = f.charAt(0).toUpperCase() + f.slice(1);
}

export function render(app) {
  const { S, SUM: U } = app;
  clock();
  const live = Date.now() - app.lastMsg < 6000 || !app.lastMsg;
  const down = S.config.services.filter(s => (S.services[s.id] || {}).up === false);
  const names = down.map(s => s.name).join(', ');
  const st = !live ? ['warn', t('no_connection')]
    : !U.known && U.total ? ['', t('checking')]
    : down.length ? ['crit', t(down.length === 1 ? 'down_one' : 'down_many', { names })]
    : ['good', t('all_good', { up: U.up, total: U.total })];
  const stHtml = `<span class="pill glass ${st[0]}"><i></i><span>${esc(st[1])}</span></span>`;
  if (cache.st !== stHtml) { $('#w-status').innerHTML = stHtml; cache.st = stHtml; }

  const tp = U.hot ? U.hot.v : null;
  const rings =
    ring(U.total ? U.up / U.total : 0, U.bad ? '#ff453a' : '#34c759', U.known ? U.up : '–', t('ring_services')) +
    ring(U.cpu != null ? U.cpu / 100 : 0, '#0a84ff', U.cpu != null ? f0(U.cpu) + '%' : '–', t('ring_cpu')) +
    ring(tp != null ? tp / 100 : 0, tp == null ? '#8e8e93' : tp >= 80 ? '#ff453a' : tp >= 65 ? '#ffd60a' : '#34c759',
         tp != null ? f0(tp) + '°' : '–', t('ring_temp')) +
    ring(U.size ? U.used / U.size : 0, '#ff9f0a', U.size ? f0(100 * U.used / U.size) + '%' : '–', t('ring_disk'));
  if (cache.rings !== rings) { $('#w-rings').innerHTML = rings; cache.rings = rings; }
  renderHostCards(S);

  for (const s of S.config.services) {
    const el = appEls[s.id];
    if (!el) continue;
    const x = S.services[s.id] || {};
    const cls = 'app' + (x.up == null && s.check !== 'none' ? ' wait' : x.up === false ? ' down' : '');
    if (el.className !== cls) el.className = cls;
    const b = el.querySelector('.badge'), hide = x.up !== false;
    if (b.hidden !== hide) b.hidden = hide;
  }
}

/* ------------------------------------------------------------------ one small card per host */

function spark(points, key, max = 100) {
  const pts = points.slice(-180).filter(p => p[key] != null);
  if (pts.length < 2) return '';
  const t0 = pts[0].t, span = pts[pts.length - 1].t - t0 || 1;
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${(100 * (p.t - t0) / span).toFixed(1)} ${(28 - 26 * Math.min(1, p[key] / max)).toFixed(1)}`).join('');
  return `<svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none"><path d="${d}"/></svg>`;
}

function mini(label, frac, text, cls = '') {
  const p = Math.max(0, Math.min(1, frac || 0));
  return `<div class="mini ${cls}"><span>${label}</span><b class="num">${text}</b><i><s style="width:${(p * 100).toFixed(0)}%"></s></i></div>`;
}

function renderHostCards(S) {
  const html = S.config.hosts.map(h => {
    const st = S.hosts[h.id] || {}, d = st.data;
    const temp = pkgTemp(st);
    const figs = d ? mini(t('cpu'), d.cpu.total / 100, f0(d.cpu.total) + '%') +
      mini(t('memory'), d.mem.used / d.mem.total, f0(100 * d.mem.used / d.mem.total) + '%') +
      (temp != null ? mini(t('ring_temp'), temp / 100, f0(temp) + '°', temp >= 80 ? 'crit' : temp >= 65 ? 'warn' : '') : '') : '';
    return `<button class="hostcard glass" type="button">
      <div class="hc-top"><span class="st ${st.online ? 'good' : 'crit'}"><i></i></span><b>${esc(h.name)}</b><span class="muted">${esc(h.description)}</span></div>
      ${spark(st.live || [], 'cpu')}
      <div class="minis">${figs || `<span class="muted">${t('no_data')}</span>`}</div>
    </button>`;
  }).join('');
  if (cache.hosts !== html) { $('#hostcards').innerHTML = html; cache.hosts = html; }
}

/* ------------------------------------------------------------------ plugin cards */

let cardsTimer = null;
async function loadCards(app) {
  clearTimeout(cardsTimer);
  let cards = [];
  try { cards = await app.api('/api/cards'); } catch (e) { /* keep the old ones */ }
  $('#cards').innerHTML = cards.map(c => `
    <section class="card glass">
      <header>${icon(c.icon || 'rejilla')}${esc(c.title)}${c.extra ? `<span class="extra">${esc(c.extra)}</span>` : ''}</header>
      <div class="list">${(c.items || []).map(it => `
        <${it.url ? `a href="${esc(it.url)}" target="_blank" rel="noopener"` : 'div'} class="item">
          ${it.img ? `<img class="thumb" src="${esc(it.img)}" alt="" loading="lazy">` : ''}
          <div class="tx"><b>${esc(it.title)}</b>${it.sub ? `<span>${esc(it.sub)}</span>` : ''}
            ${it.progress != null ? `<div class="bar"><i style="width:${Math.round(it.progress * 100)}%"></i></div>` : ''}</div>
        </${it.url ? 'a' : 'div'}>`).join('') || `<p class="empty">${esc(c.empty || '')}</p>`}</div>
    </section>`).join('');
  if (cards.length) cardsTimer = setTimeout(() => loadCards(app), 30000);
}
