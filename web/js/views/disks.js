// Disks: one card per physical disk, then storage (pools, datasets, Proxmox storages) and backups.
import { $, ago, bytes, esc, f0, f1, gib, meter, tempClass } from '../fmt.js';
import { locale, t } from '../i18n.js';
import { diskHealth, guests } from '../main.js';

const diskCfg = (S, hid, x) => S.config.disks.find(c => c.host === hid && c.serial === x.serial) || {};

function usage(x, d) {
  const out = [];
  for (const m of x.mounts) {
    const f = (d.fs || []).find(f => f.mount === m);
    if (f && m !== '/boot/efi' && !m.startsWith('/boot')) out.push({ label: m === '/' ? t('root') : m, used: f.used, total: f.total });
  }
  if (x.fstypes.includes('zfs_member')) for (const p of d.zfs?.pools || []) out.push({ label: 'zpool ' + p.name, used: p.alloc, total: p.size });
  if (x.fstypes.includes('LVM2_member')) for (const s of d.storage || []) if (s.type === 'lvmthin' && s.active) out.push({ label: s.storage, used: s.used, total: s.total });
  return out;
}

export function render(app) {
  const { S } = app;
  const cards = [];
  for (const h of S.config.hosts) {
    const d = S.hosts[h.id]?.data;
    if (!d?.disks) continue;
    const order = S.config.disks.filter(c => c.host === h.id).map(c => c.serial);
    const list = [...d.disks].sort((a, b) => (order.indexOf(a.serial) + 1 || 99) - (order.indexOf(b.serial) + 1 || 99));
    for (const x of list) {
      const c = diskCfg(S, h.id, x), sm = x.smart || {}, io = d.io?.[x.name] || {}, health = diskHealth(x);
      const tc = tempClass(sm.temp, x.tran === 'nvme' ? 70 : 50, x.tran === 'nvme' ? 80 : 60);
      const use = usage(x, d);
      const tran = { sata: 'SATA', usb: 'USB', nvme: 'NVMe', sas: 'SAS' }[x.tran] || x.tran || '';
      cards.push(`<div class="disk glass">
        <div class="l1"><h4>${esc(c.label || x.name)}</h4><span class="muted">${esc(h.name)} · ${esc(x.name)}</span>
          <span class="temp num ${tc}-t">${sm.temp != null ? f0(sm.temp) + ' °C' : ''}</span></div>
        <div class="role">${esc(c.role || (c.label ? '' : t('uncatalogued')))}</div>
        ${use.slice(0, 2).map(u => `<div class="use">${meter(u.used / u.total)}<span class="num">${gib(u.used)} / ${gib(u.total)}</span>&nbsp;<span class="muted">${esc(u.label)}</span></div>`).join('')
          || `<div class="use muted">${x.mounts.length ? '' : t('not_mounted')}</div>`}
        <dl>
          <dt>${t('health')}</dt><dd><span class="st ${health[0]}"><i></i>${health[1]}</span></dd>
          <dt>${t('model')}</dt><dd title="${esc(x.model)} · ${esc(x.serial)}">${esc(x.model || '–')} <span class="muted">· ${esc(tran)} · ${gib(x.size)}</span></dd>
          <dt>${t('usage')}</dt><dd class="num">${sm.hours != null ? f0(sm.hours) + ' h' + ` <span class="muted">(${f1(sm.hours / 8760)} ${t('years')})</span>` : '–'}${sm.wear != null ? ` · ${t('wear')} ${sm.wear} %` : ''}</dd>
          <dt>${t('now_io')}</dt><dd class="num ink2">↓ ${bytes(io.read)}/s · ↑ ${bytes(io.write)}/s · ${f0(io.busy || 0)} %</dd>
        </dl></div>`);
    }
  }
  $('#disks').innerHTML = cards.join('');
  renderStorage(S);
  renderBackups(S);
}

function renderStorage(S) {
  const rows = [];
  const multi = S.config.hosts.length > 1;
  for (const h of S.config.hosts) {
    const d = S.hosts[h.id]?.data;
    if (!d) continue;
    const where = multi ? `<td class="muted">${esc(h.name)}</td>` : '';
    const pools = d.zfs?.pools || [];
    for (const p of pools) {
      rows.push(`<tr><td><b>${esc(p.name)}</b><span class="tag">zpool</span> <span class="st ${p.health === 'ONLINE' ? 'good' : 'crit'}"><i></i>${esc(p.health)}</span></td><td>${meter(p.alloc / p.size)}</td><td class="r num">${gib(p.alloc)} <span class="muted">/ ${gib(p.size)}</span></td>${where}</tr>`);
      for (const ds of d.zfs.datasets.filter(z => z.name.split('/').length === 2 && z.name.startsWith(p.name + '/')))
        rows.push(`<tr><td class="ink2 indent">${esc(ds.name)} <span class="muted small">×${esc(ds.ratio.replace('x', ''))}</span></td><td>${meter(ds.used / (ds.used + ds.avail))}</td><td class="r num">${gib(ds.used)}</td>${where}</tr>`);
    }
    for (const f of d.fs || []) {
      if (f.type === 'zfs' || f.mount.startsWith('/boot')) continue;
      rows.push(`<tr><td>${esc(f.mount)}<span class="tag">${esc(f.type)}</span></td><td>${meter(f.used / f.total)}</td><td class="r num">${gib(f.used)} <span class="muted">/ ${gib(f.total)}</span></td>${where}</tr>`);
    }
    for (const s of d.storage || []) {
      if (!s.active || s.type !== 'lvmthin') continue;      // dir storages are already listed as filesystems
      rows.push(`<tr><td>${esc(s.storage)}<span class="tag">${esc(s.type)}</span></td><td>${meter(s.used / s.total)}</td><td class="r num">${gib(s.used)} <span class="muted">/ ${gib(s.total)}</span></td>${where}</tr>`);
    }
  }
  $('#storage').innerHTML = `<tbody>${rows.join('')}</tbody>`;
}

// last vzdump per guest and backup storage: green if recent, amber if late, red if missing
function renderBackups(S) {
  const gi = guests(), now = Date.now() / 1000;
  const rows = [];
  let cols = [];
  for (const h of S.config.hosts) {
    const b = S.hosts[h.id]?.data?.backups;
    if (!b || !Object.keys(b).length) continue;
    cols = Object.keys(b);
    // how old a backup may be before it counts as late: [backup_max_age] in faro.toml, in hours
    const limits = S.config.backup_max_age;
    const rhythm = Object.fromEntries(cols.map(c => [c, (limits[c] ?? limits.default) * 3600]));
    const ids = Object.values(gi).filter(g => g.host === h.id).map(g => String(g.vmid));
    for (const id of ids) {
      if (!cols.some(c => b[c].guests[id])) continue;      // never backed up anywhere: probably on purpose
      rows.push(`<tr><td><span class="muted num">${id}</span> ${esc(gi[h.id + ':' + id]?.name)}</td>${cols.map(c => cell(b[c].guests[id]?.ts, rhythm[c], now)).join('')}</tr>`);
    }
  }
  $('#backups-box').hidden = !rows.length;
  $('#backups').innerHTML = rows.length ? `<thead><tr><th>${t('what')}</th>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody>` : '';
}

function cell(ts, maxAge, now) {
  if (!ts) return `<td><span class="st crit"><i></i>${t('none_yet')}</span></td>`;
  const age = now - ts, cls = age < maxAge ? 'good' : age < maxAge * 2 ? 'warn' : 'crit';
  return `<td title="${new Date(ts * 1000).toLocaleString(locale())}"><span class="st ${cls}"><i></i>${ago(ts)}</span></td>`;
}
