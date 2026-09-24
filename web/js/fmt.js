// Formatting helpers shared by every view.
import { locale, t } from './i18n.js';

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const nfCache = {};
export const nf = (d = 0) => (nfCache[locale() + d] ||= new Intl.NumberFormat(locale(), { minimumFractionDigits: d, maximumFractionDigits: d }));
export const f0 = v => nf(0).format(v);
export const f1 = v => nf(1).format(v);

export function bytes(n, d = 1) {
  if (n == null) return '–';
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0;
  while (Math.abs(n) >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return (i === 0 ? f0(n) : nf(n >= 100 ? 0 : d).format(n)) + ' ' + u[i];
}

// binary units for disks and RAM, like Proxmox
export function gib(n) {
  if (n == null) return '–';
  const u = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return nf(n >= 100 || i < 2 ? 0 : 1).format(n) + ' ' + u[i];
}

export function rate(bps) {
  if (bps == null) return '–';
  const bits = bps * 8;
  if (bits < 1e3) return f0(bits) + ' b/s';
  if (bits < 1e6) return f0(bits / 1e3) + ' kb/s';
  if (bits < 1e9) return nf(bits < 1e7 ? 1 : 0).format(bits / 1e6) + ' Mb/s';
  return f1(bits / 1e9) + ' Gb/s';
}

export function dur(s) {
  if (!s) return '–';
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}

export function ago(ts) {
  if (!ts) return t('never');
  const s = Date.now() / 1000 - ts;
  if (s < 90) return t('just_now');
  if (s < 3600) return t('min_ago', { n: Math.round(s / 60) });
  if (s < 86400 * 2) return t('h_ago', { n: Math.round(s / 3600) });
  return t('d_ago', { n: Math.round(s / 86400) });
}

export const hhmm = ts => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
export const hms = ts => new Date(ts * 1000).toLocaleTimeString(locale());
export const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
export const tempClass = (v, warn = 70, crit = 85) => v == null ? '' : v >= crit ? 'crit' : v >= warn ? 'warn' : '';

export function meter(frac) {
  const p = Math.max(0, Math.min(1, frac || 0));
  return `<span class="meter ${p > .95 ? 'full' : p > .85 ? 'hi' : ''}"><b style="width:${(p * 100).toFixed(1)}%"></b></span>`;
}

export const store = {
  get(k) { try { return JSON.parse(localStorage.getItem('faro-' + k)); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem('faro-' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
