// Services: status table with response times and history, then guests without a service.
import { $, ago, dur, esc, f0, f1, gib, hms, meter, rate } from '../fmt.js';
import { t } from '../i18n.js';
import { appIcon } from '../icons.js';
import { guests } from '../main.js';
import * as sheet from './sheet.js';

export function strip(hist, n = 60) {
  const h = (hist || []).slice(-n);
  return `<span class="strip">${'<i class="none"></i>'.repeat(n - h.length)}${h.map(x =>
    `<i class="${x[1] ? '' : 'down'}" title="${hms(x[0])} · ${x[1] ? (x[2] != null ? f0(x[2]) + ' ms' : 'ok') : t('not_responding')}"></i>`).join('')}</span>`;
}

export function reasonText(code) {
  if (code == null) return '';
  return typeof code === 'number' ? 'HTTP ' + code : t('reason')[code] || code;
}

export function guestNet(app, hid, g) {
  const n = app.S.hosts[hid]?.data?.net?.[g.iface];
  return n ? { dn: n.tx, up: n.rx } : null;      // the host's tx on the guest's interface is the guest's download
}

export function build() {
  $('#svc').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-s]');
    if (tr && !e.target.closest('a')) sheet.open('app', tr.dataset.s);
  });
  $('#tiles').addEventListener('click', e => {
    const b = e.target.closest('[data-g]');
    if (b) sheet.open('guest', b.dataset.g);
  });
}

export function render(app) {
  const { S } = app;
  const gi = guests();
  const rows = S.config.services.map(c => {
    const s = S.services[c.id] || {}, g = c.guest != null ? gi[`${c.host}:${c.guest}`] : null;
    const net = g ? guestNet(app, c.host, g) : null, hist = s.history || [];
    const avail = hist.length ? hist.filter(x => x[1]).length / hist.length : null;
    const state = c.check === 'none' && !S.services[c.id] ? ['idle', t('no_check')]
      : s.up == null ? ['idle', t('checking_s')] : s.up ? ['good', t('responds')] : ['crit', t('not_responding')];
    const host = S.config.hosts.find(h => h.id === c.host);
    const where = g ? `${g.kind === 'lxc' ? 'CT' : 'VM'} ${g.vmid}` : host ? host.name : '';
    const addr = c.url ? c.url.replace(/^https?:\/\//, '').replace(/\/$/, '') : c.target || '';
    return `<tr data-s="${esc(c.id)}">
      <td><span class="st ${state[0]}"><i></i>${state[1]}</span>${s.up === false && s.code != null ? `<span class="sub">${esc(reasonText(s.code))}</span>` : ''}</td>
      <td><div class="svc-n">${appIcon(c)}<div>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.name)}</a>` : `<b>${esc(c.name)}</b>`}<span class="sub">${esc(c.description)}</span></div></div></td>
      <td class="mono">${esc(addr)}</td>
      <td class="muted">${esc(where)}</td>
      <td class="r num">${s.ms != null ? f0(s.ms) + ' ms' : '–'}</td>
      <td>${strip(hist)}<span class="sub">${avail == null ? '' : t('available', { p: f1(avail * 100) })}</span></td>
      <td class="r num">${g && g.status === 'running' ? (g.cpu < 10 ? f1(g.cpu) : f0(g.cpu)) + ' %' : '–'}</td>
      <td>${g && g.maxmem ? meter(g.mem / g.maxmem) + `<span class="num">${gib(g.mem)}</span><span class="sub">${t('of')} ${gib(g.maxmem)}</span>` : '–'}</td>
      <td>${g && g.maxdisk ? meter(g.disk / g.maxdisk) + `<span class="num">${gib(g.disk)}</span><span class="sub">${t('of')} ${gib(g.maxdisk)}</span>` : '–'}</td>
      <td class="io num">${net ? `<span class="dn">${rate(net.dn)}</span><br><span class="up">${rate(net.up)}</span>` : '–'}</td>
      <td class="r num">${g ? dur(g.uptime) : ''}${s.since && s.up != null ? `<span class="sub">${t(s.up ? 'stable_since' : 'down_since', { ago: ago(s.since) })}</span>` : ''}</td>
    </tr>`;
  });
  const heads = ['status', 'service', 'address', 'where', 'response', null, 'cpu', 'memory', 'disks', 'ch_net', 'uptime'];
  $('#svc').innerHTML = `<thead><tr>${heads.map((h, i) => `<th class="${[4, 6, 10].includes(i) ? 'r' : ''}" data-l="${h ? esc(t(h)) : ''}">${h ? t(h) : t('last_checks', { n: 60 })}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody>`;
  // phones turn each row into a card: the labels come from the header
  const labels = heads.map(h => (h ? t(h) : t('last_checks', { n: 60 })));
  for (const tr of $('#svc tbody').children) [...tr.children].forEach((td, i) => { td.dataset.l = labels[i]; });

  const last = Math.max(0, ...Object.values(S.services).map(s => s.checked || 0));
  $('#svc-note').textContent = last ? t('checked', { ago: ago(last), n: S.config.check_interval }) : '';

  const linked = new Set(S.config.services.filter(s => s.guest != null).map(s => `${s.host}:${s.guest}`));
  const rest = Object.entries(gi).filter(([k]) => !linked.has(k))
    .sort((a, b) => a[1].host.localeCompare(b[1].host) || a[1].vmid - b[1].vmid);
  $('#others-h').hidden = !rest.length;
  $('#tiles').innerHTML = rest.map(([key, g]) => {
    const run = g.status === 'running', net = guestNet(app, g.host, g);
    const host = S.config.hosts.find(h => h.id === g.host);
    return `<button class="tile glass" type="button" data-g="${esc(key)}">
      <div class="n"><span class="st ${run ? 'good' : 'idle'}"><i></i></span><b>${esc(g.name)}</b><span class="tag">${g.kind === 'lxc' ? 'CT' : 'VM'} ${g.vmid}</span><span class="muted">${esc(host?.name)}</span></div>
      <div class="s">${esc(S.config.guests[key] || '')}${g.ip ? (S.config.guests[key] ? ' · ' : '') + esc(g.ip) : ''}</div>
      <div class="m">${run ? `<span class="num">CPU ${f1(g.cpu)} %</span><span class="num">${gib(g.mem)} / ${gib(g.maxmem)}</span>${net ? `<span class="io num"><span class="dn">${rate(net.dn)}</span></span>` : ''}`
        : `<span class="muted">${t('stopped')} · ${g.cpus} ${t('cores')} · ${gib(g.maxmem)}</span>`}</div>
    </button>`;
  }).join('');
}
