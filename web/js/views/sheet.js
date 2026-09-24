// Bottom sheet: settings, details of an app or guest, and the alert log.
import { $, ago, dur, esc, f0, f1, gib, store } from '../fmt.js';
import { LANGS, getLanguage, locale, t } from '../i18n.js';
import { appIcon, icon } from '../icons.js';
import { app, applyEffects, applyTheme, guests, logout } from '../main.js';
import { reasonText, strip } from './services.js';

let current = null;       // {kind, id}
let lastHtml = '';

export function open(kind, id) {
  current = { kind, id };
  lastHtml = '';
  $('#veil').hidden = false;
  $('#sheet').hidden = false;
  $('#sheet').classList.toggle('tall', kind === 'alerts' || (kind === 'element' && id.dataset.tall != null));
  if (kind === 'element') $('#sheet-body').replaceChildren(id);     // a plugin's own content
  else paint();
  if (kind === 'alerts') loadAlerts();
  history.pushState({ sheet: kind }, '');
}

export function close(fromHistory) {
  if (!current) return;
  current = null;
  $('#veil').hidden = true;
  $('#sheet').hidden = true;
  if (!fromHistory && history.state?.sheet) history.back();
}

$('#veil').onclick = () => close();
addEventListener('popstate', () => { if (current) close(true); });

// live data (response time, guest CPU) keeps updating while the sheet is open
export function refresh() {
  if (current && (current.kind === 'app' || current.kind === 'guest')) paint();
}

function paint() {
  const html = { settings, app: appSheet, guest: guestSheet, alerts: alertsSheet }[current.kind](current.id);
  if (html === lastHtml) return;
  lastHtml = html;
  $('#sheet-body').innerHTML = html;
}

/* ------------------------------------------------------------------ settings */

function seg(id, options, value) {
  return `<span class="seg" id="${id}">${options.map(([v, label]) =>
    `<button type="button" data-v="${esc(v)}" class="${v === value ? 'on' : ''}">${esc(label)}</button>`).join('')}</span>`;
}

function settings() {
  const theme = store.get('theme') || '';
  const effects = store.get('effects') !== false;
  return `<h3>${t('settings')}</h3>
    <div class="opt"><span>${t('theme')}</span>${seg('o-theme', [['', t('auto')], ['light', t('light')], ['dark', t('dark')]], theme)}</div>
    <div class="opt"><span>${t('language')}</span>${seg('o-lang', Object.entries(LANGS), getLanguage())}</div>
    <div class="opt"><span>${t('effects')}<small>${t('effects_note')}</small></span>
      <button class="switch ${effects ? 'on' : ''}" id="o-effects" type="button" role="switch" aria-checked="${effects}" aria-label="${t('effects')}"></button></div>
    <div class="opt"><span>${t('version')}</span><span class="muted num">faro ${esc(app.S.version)}${app.S.demo ? ' · demo' : ''}</span></div>
    <p class="note">${t('long_press')}</p>
    <div class="acts">
      <button class="btn" id="o-test" type="button">${icon('campana')}${t('test_notify')}</button>
      <button class="btn" id="o-logout" type="button">${icon('salir')}${t('logout')}</button>
    </div>`;
}

$('#sheet-body').addEventListener('click', async e => {
  const b = e.target.closest('button');
  if (!b) return;
  const group = b.closest('.seg')?.id;
  if (group === 'o-theme') { store.set('theme', b.dataset.v || null); applyTheme(b.dataset.v); }
  if (group === 'o-lang') { try { localStorage.setItem('faro-lang', b.dataset.v); } catch (err) { /* ignore */ } location.reload(); }
  if (b.id === 'o-effects') { const on = !b.classList.contains('on'); store.set('effects', on); applyEffects(on); }
  if (b.id === 'o-test') {
    const r = await app.api('/api/alerts/test', {});
    app.toast(r.notifiers ? t('notify_sent') : t('notify_none'));
  }
  if (b.id === 'o-logout') logout();
  if (b.dataset.op) power(b);
  if (b.dataset.filter) { filter = b.dataset.filter; lastHtml = ''; paint(); }
  if (group || b.id === 'o-effects') { lastHtml = ''; paint(); }
});

/* ------------------------------------------------------------------ app and guest details */

function powerButtons(hostId, g) {
  const host = app.S.config.hosts.find(h => h.id === hostId);
  if (!host?.actions || !g || !app.S.actions.some(a => a.id === 'guest.power')) return '';
  const ops = g.status === 'running' ? ['shutdown', 'reboot'] : ['start'];
  return `<div class="acts">${ops.map(op => `<button class="btn" type="button" data-op="${op}" data-host="${esc(hostId)}" data-vmid="${g.vmid}">${icon('power')}${t(op)}</button>`).join('')}</div>`;
}

// destructive actions ask for a second tap instead of a modal dialog
async function power(b) {
  if (b.dataset.op !== 'start' && !b.classList.contains('confirm')) {
    b.classList.add('confirm');
    b.dataset.label = b.textContent;
    b.lastChild.textContent = t('confirm_again');
    setTimeout(() => { if (b.isConnected) { b.classList.remove('confirm'); b.lastChild.textContent = b.dataset.label; } }, 4000);
    return;
  }
  b.disabled = true;
  b.lastChild.textContent = t('working');
  const r = await app.api('/api/action', { id: 'guest.power', params: { host: b.dataset.host, vmid: +b.dataset.vmid, op: b.dataset.op } });
  app.toast(r.text, !r.ok);
  lastHtml = '';
}

function guestFacts(g) {
  if (!g) return '';
  const run = g.status === 'running';
  return `<dt>${t('guest')}</dt><dd>${g.kind === 'lxc' ? 'CT' : 'VM'} ${g.vmid} · ${esc(g.name)} · <span class="st ${run ? 'good' : 'idle'}"><i></i>${run ? dur(g.uptime) : t('stopped')}</span></dd>
    ${run ? `<dt>${t('cpu')}</dt><dd class="num">${f1(g.cpu)} % · ${g.cpus} ${t('cores')}</dd>
    <dt>${t('memory')}</dt><dd class="num">${gib(g.mem)} ${t('of')} ${gib(g.maxmem)}</dd>` : ''}
    ${g.ip ? `<dt>IP</dt><dd class="mono">${esc(g.ip)}</dd>` : ''}`;
}

function appSheet(id) {
  const c = app.S.config.services.find(s => s.id === id);
  if (!c) return '';
  const s = app.S.services[id] || {}, hist = s.history || [];
  const g = c.guest != null ? guests()[`${c.host}:${c.guest}`] : null;
  const avail = hist.length ? hist.filter(x => x[1]).length / hist.length : null;
  const state = s.up == null ? ['idle', c.check === 'none' ? t('no_check') : t('checking_s')] : s.up ? ['good', t('responds')] : ['crit', t('not_responding')];
  return `<div class="ah">${appIcon(c)}<div><h3>${esc(c.name)}</h3><p>${esc(c.description)}</p></div></div>
    <dl class="kv">
      <dt>${t('status')}</dt><dd><span class="st ${state[0]}"><i></i>${state[1]}</span>${s.up === false ? ' · ' + esc(reasonText(s.code)) : ''}${s.since && s.up != null ? ` <span class="muted">· ${ago(s.since)}</span>` : ''}</dd>
      ${s.ms != null ? `<dt>${t('response_time')}</dt><dd class="num">${f0(s.ms)} ms</dd>` : ''}
      ${hist.length ? `<dt>${t('availability')}</dt><dd>${strip(hist, 45)} <span class="num">${f1(avail * 100)} %</span></dd>` : ''}
      ${c.url ? `<dt>${t('address')}</dt><dd class="mono">${esc(c.url)}</dd>` : ''}
      ${guestFacts(g)}
    </dl>
    ${c.url ? `<div class="acts"><a class="btn primary" href="${esc(c.url)}" target="_blank" rel="noopener">${t('open_url', { name: esc(c.name) })}</a></div>` : ''}
    ${powerButtons(c.host, g)}`;
}

function guestSheet(key) {
  const g = guests()[key];
  if (!g) return '';
  const host = app.S.config.hosts.find(h => h.id === g.host);
  return `<div class="ah"><span class="ico" style="--a:#5b6478;--a2:#363c49">${icon(g.kind === 'lxc' ? 'capas' : 'servidor')}</span>
      <div><h3>${esc(g.name)}</h3><p>${esc(app.S.config.guests[key] || host?.name || '')}</p></div></div>
    <dl class="kv">${guestFacts(g)}</dl>${powerButtons(g.host, g)}`;
}

/* ------------------------------------------------------------------ alerts */

let alerts = [], filter = 'all';
async function loadAlerts() {
  try { alerts = await app.api('/api/alerts?n=200'); } catch (e) { alerts = []; }
  lastHtml = '';
  paint();
}

function dayLabel(ts) {
  const d = new Date(ts * 1000), today = new Date();
  const days = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 864e5);
  return days === 0 ? t('today') : d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' });
}

function alertsSheet() {
  const list = alerts.filter(a => filter === 'all' || a.level === 'bad');
  let lastDay = '';
  const rows = list.map(a => {
    const day = dayLabel(a.ts);
    const head = day !== lastDay ? `<h4>${esc(day)}</h4>` : '';
    lastDay = day;
    return `${head}<div class="alert ${a.level}"><i></i><div><b>${esc(a.title)}</b>${a.body ? `<span>${esc(a.body)}</span>` : ''}</div>
      <time>${new Date(a.ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })}</time></div>`;
  }).join('');
  return `<h3>${t('alerts')}</h3>
    <div class="seg filters">${[['all', t('all')], ['bad', t('problems')]].map(([v, l]) =>
      `<button type="button" data-filter="${v}" class="${filter === v ? 'on' : ''}">${l}</button>`).join('')}</div>
    <div class="alerts">${rows || `<p class="note">${t('no_alerts')}</p>`}</div>`;
}

