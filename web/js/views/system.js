// System: one card per host with live figures, charts, per-thread load and sensors.
import { Chart } from '../chart.js';
import { $, $$, bytes, dur, esc, f0, f1, gib, rate, tempClass } from '../fmt.js';
import { t } from '../i18n.js';
import { pkgTemp } from '../main.js';

let range = 'live';
const hostCharts = {};

const niceRate = m => [125e3, 1.25e6, 6.25e6, 12.5e6, 62.5e6, 125e6, 1.25e9].find(s => s >= m * 1.1) || m * 1.2;
const CHARTS = {
  temp: { title: 'ch_temp', big: true, smooth: 5, min: 20, floor: 60, nice: m => Math.ceil((m + 3) / 10) * 10, fmt: v => f0(v) + ' °C',
          series: [{ k: 'temp', c: '--s1', label: 's_cpu_med' }, { k: 'disk', c: '--s2', label: 's_disk_hot' }] },
  cpu:  { title: 'ch_cpu', min: 0, max: 100, fmt: v => f0(v) + ' %', area: true, series: [{ k: 'cpu', c: '--s1', label: 'cpu' }] },
  net:  { title: 'ch_net', half: true, min: 0, floor: 125e3, nice: niceRate, fmt: rate,
          series: [{ k: 'rx', c: '--s1', label: 's_down' }, { k: 'tx', c: '--s2', label: 's_up' }] },
  mem:  { title: 'ch_mem', half: true, min: 0, max: 100, fmt: v => f0(v) + ' %', area: true, series: [{ k: 'mem', c: '--s1', label: 's_ram' }] },
};

// consecutive "half" charts share a row
function chartsHtml() {
  const one = ([k, c]) => `<div class="chart ${c.big ? 'big' : ''}"><div class="hd"><b>${t(c.title)}</b>${c.series.length > 1
    ? c.series.map(s => `<span class="key"><i style="background:var(${s.c})"></i>${t(s.label)}</span>`).join('') : ''}</div><div class="box" data-c="${k}"></div></div>`;
  let html = '', row = [];
  const flush = () => { if (row.length) html += `<div class="chart-row">${row.map(one).join('')}</div>`; row = []; };
  for (const e of Object.entries(CHARTS)) { if (e[1].half) row.push(e); else { flush(); html += one(e); } }
  flush();
  return html;
}

export function build(app) {
  const root = $('#hosts');
  root.innerHTML = '';
  for (const h of app.S.config.hosts) {
    const el = document.createElement('div');
    el.className = 'host glass';
    el.id = 'h-' + h.id;
    el.innerHTML = `
      <div class="name"><h3>${esc(h.name)}</h3><span class="st" data-f="status"></span><span class="role">${esc(h.description)}</span></div>
      <div class="meta" data-f="meta"></div>
      <div class="figs">
        <div class="fig"><div class="k">${t('cpu')}</div><div class="v num" data-f="cpu">–</div><div class="d" data-f="load"></div></div>
        <div class="fig"><div class="k">${t('cpu_temp')}</div><div class="v num" data-f="temp">–</div><div class="d" data-f="tempmax"></div></div>
        <div class="fig"><div class="k">${t('memory')}</div><div class="v num" data-f="mem">–</div><div class="d" data-f="memd"></div></div>
        <div class="fig"><div class="k">${t('net_now')}</div><div class="v sm num" data-f="net"></div><div class="d" data-f="netd"></div></div>
      </div>
      <div data-f="offline"></div>
      <div class="charts">${chartsHtml()}</div>
      <div class="lower">
        <div><div class="hd" data-f="coreshd"></div><div class="cores" data-f="cores"></div></div>
        <div><div class="hd">${t('sensors')}</div><div class="sensors" data-f="sensors"></div></div>
      </div>
      <div data-f="containers"></div>`;
    root.append(el);
    hostCharts[h.id] = {};
    $$('[data-c]', el).forEach(b => { hostCharts[h.id][b.dataset.c] = new Chart(b, CHARTS[b.dataset.c]); });
  }
  $('#range').onclick = e => {
    const b = e.target.closest('button');
    if (!b) return;
    range = b.dataset.r;
    $$('#range button').forEach(x => x.classList.toggle('on', x === b));
    render(app);
  };
}

function sensorLabel(s) {
  if (s.chip === 'acpitz') return 'ACPI';
  if (s.chip === 'nvme') return 'NVMe ' + s.label.replace('Sensor ', 's');
  return s.label;
}

export function render(app) {
  const { S } = app;
  for (const h of S.config.hosts) {
    const st = S.hosts[h.id] || {}, d = st.data, el = $('#h-' + h.id);
    if (!el) continue;
    const F = k => el.querySelector(`[data-f="${k}"]`);
    const status = F('status');
    status.className = 'st ' + (st.online ? 'good' : 'crit');
    status.innerHTML = `<i></i>${st.online ? t('online') : t('no_data')}`;
    F('offline').innerHTML = st.online ? '' :
      `<div class="offline">${esc(t('offline_msg', { name: h.name, address: h.address }))} ${st.error ? '<span class="mono">' + esc(st.error) + '</span> ' : ''}${t('retrying')}</div>`;
    if (!d) continue;

    const cpuModel = (d.host.cpu_model || '').replace(/\(R\)|\(TM\)|CPU|@.*$|with Radeon.*$/g, '').replace(/\s+/g, ' ').trim();
    F('meta').textContent = [d.host.node, h.address, cpuModel, `${d.host.threads} ${t('threads')}`,
      d.host.pve ? 'Proxmox ' + d.host.pve : d.host.os, d.host.container ? d.host.container.toUpperCase() : '',
      t('up_for', { d: dur(d.uptime) })].filter(Boolean).join(' · ');
    F('cpu').innerHTML = `${f0(d.cpu.total)}<small>%</small>`;
    F('load').textContent = t('load') + ' ' + d.load.map(v => f1(v)).join(' · ');
    const pkg = pkgTemp(st), peak = Math.max(0, ...(st.live || []).map(p => p.temp ?? 0));
    const tc = tempClass(pkg, 75, 90);
    F('temp').innerHTML = pkg != null ? `<span class="${tc}-t">${f0(pkg)}</span><small>°C</small>` : '–';
    F('tempmax').textContent = peak ? t('peak_15', { v: f0(peak) }) : '';
    F('mem').innerHTML = `${f0(100 * d.mem.used / d.mem.total)}<small>%</small>`;
    F('memd').textContent = `${gib(d.mem.used)} ${t('of')} ${gib(d.mem.total)}` + (d.mem.arc > 2 ** 28 ? ` · ARC ${gib(d.mem.arc)}` : '');
    const nicName = h.nic || d.nic, nic = d.net[nicName] || {};
    F('net').innerHTML = `<span class="io"><span class="dn">${rate(nic.rx)}</span></span><br><span class="io"><span class="up">${rate(nic.tx)}</span></span>`;
    F('netd').textContent = nicName ? `${nicName} · ${bytes(nic.rx_total)} ↓ ${bytes(nic.tx_total)} ↑` : '';
    F('cores').innerHTML = d.cpu.cores.map((c, i) => `<span title="${i}: ${f0(c)} %" style="height:${Math.max(3, c)}%"></span>`).join('');
    F('coreshd').textContent = t('per_thread', { n: d.cpu.cores.length });

    const diskTemps = (d.disks || []).filter(x => x.smart?.temp != null).map(x => {
      const c = S.config.disks.find(c => c.host === h.id && c.serial === x.serial);
      return { label: c?.label || x.name, value: x.smart.temp };
    });
    const sens = d.temps.filter(s => !(s.chip === 'nvme' && s.label === 'Composite')).map(s => ({ label: sensorLabel(s), value: s.value }));
    F('sensors').innerHTML = [...sens, ...diskTemps].map(s => {
      const c = tempClass(s.value, 80, 95);
      return `<div><span title="${esc(s.label)}">${esc(s.label)}</span><span class="num ${c}-t">${f0(s.value)} °C</span></div>`;
    }).join('');

    const cts = d.containers || [];
    F('containers').innerHTML = cts.length ? `<div class="hd ctr-h">${t('containers')} · ${cts.length}</div><div class="ctrs">${cts.map(c =>
      `<span class="ctr" title="${esc(c.image)} · ${esc(c.status)}"><span class="st ${c.state === 'running' ? 'good' : 'idle'}"><i></i></span>${esc(c.name)}</span>`).join('')}</div>` : '';

    const sr = range === 'live' ? { data: st.live || [], span: 900 } : { data: st.day || [], span: 86400 };
    for (const k in hostCharts[h.id]) hostCharts[h.id][k].set(sr.data, sr.span);
  }
}
