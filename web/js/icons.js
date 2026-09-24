// Line icons (24x24, stroke). A service's `icon` can be one of these names or an image URL.
import { esc } from './fmt.js';

export const ICONS = {
  play: '<path d="M8.5 5.2 18 12l-9.5 6.8z" fill="currentColor" stroke-width="1.2" stroke-linejoin="round"/>',
  musica: '<path d="M9 17.5V5l10-2v12.5"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="15.5" r="2.5"/>',
  sync: '<path d="M20.5 12a8.5 8.5 0 0 1-14.3 6.2"/><path d="M3.5 12a8.5 8.5 0 0 1 14.3-6.2"/><path d="M17.5 2.2v3.8h-3.8"/><path d="M6.5 21.8V18h3.8"/>',
  descarga: '<path d="M12 3.5v10"/><path d="m8 10 4 4 4-4"/><path d="M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/>',
  nube: '<path d="M17.3 19H8.5a5.5 5.5 0 1 1 5.2-7.3"/><path d="M13.7 11.7a4 4 0 1 1 3.6 7.3"/>',
  carpeta: '<path d="M4 7.2A1.7 1.7 0 0 1 5.7 5.5h3.5a1.7 1.7 0 0 1 1.4.75l.9 1.35h6.8A1.7 1.7 0 0 1 20 9.25v8A1.7 1.7 0 0 1 18.3 19H5.7A1.7 1.7 0 0 1 4 17.25z"/>',
  llave: '<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.2-8.2M16 7l2.5 2.5M13.5 9.5 15.5 11.5"/>',
  escudo: '<path d="M12 3 5.5 5.6v5.8c0 4 2.6 7.3 6.5 8.6 3.9-1.3 6.5-4.6 6.5-8.6V5.6z"/><path d="m9.3 11.8 2 2 3.4-3.6"/>',
  grafica: '<path d="M4 4v15.5h16"/><path d="m7.5 15 3.2-4.2 2.9 2.4L19 7.5"/>',
  base: '<ellipse cx="12" cy="6" rx="6.8" ry="2.8"/><path d="M5.2 6v11.8c0 1.6 3 2.9 6.8 2.9s6.8-1.3 6.8-2.9V6"/><path d="M5.2 11.9c0 1.6 3 2.9 6.8 2.9s6.8-1.3 6.8-2.9"/>',
  capas: '<path d="m12 3.2 8 4.3-8 4.3-8-4.3z"/><path d="m4 12 8 4.3 8-4.3"/><path d="m4 16.5 8 4.3 8-4.3"/>',
  servidor: '<rect x="3.5" y="4.5" width="17" height="6" rx="2"/><rect x="3.5" y="13.5" width="17" height="6" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  candado: '<rect x="4.5" y="10.5" width="15" height="9.5" rx="2.5"/><path d="M8 10.5V7.2a4 4 0 0 1 8 0v3.3"/>',
  casa: '<path d="M4 10.4 12 4l8 6.4V19a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19z"/><path d="M9.5 20.5v-6h5v6"/>',
  chip: '<rect x="4.5" y="4.5" width="15" height="15" rx="3.5"/><rect x="9" y="9" width="6" height="6" rx="1.5"/><path d="M9 2.6v1.9M15 2.6v1.9M9 19.5v1.9M15 19.5v1.9M2.6 9h1.9M2.6 15h1.9M19.5 9h1.9M19.5 15h1.9"/>',
  rejilla: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
  disco: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.4"/><path d="M12 3.5v3"/>',
  ajustes: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>',
  peli: '<rect x="4" y="4.5" width="16" height="15" rx="2"/><path d="M8 4.5v15M16 4.5v15M4 9.5h4M4 14.5h4M16 9.5h4M16 14.5h4"/>',
  campana: '<path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  atras: '<path d="m14.5 5-7 7 7 7"/>',
  red: '<circle cx="12" cy="5.5" r="2"/><circle cx="5.5" cy="18.5" r="2"/><circle cx="18.5" cy="18.5" r="2"/><path d="M12 7.5v5M12 12.5l-5 4.5M12 12.5l5 4.5"/>',
  terminal: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="m7.5 9.5 3 2.5-3 2.5M12.5 15h4"/>',
  camara: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.5"/>',
  correo: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
  libro: '<path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12.5H7.5A2.5 2.5 0 0 1 5 17z"/><path d="M5 17a2.5 2.5 0 0 1 2.5-2.5H18"/>',
  salir: '<path d="M14 4.5h3.5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H14"/><path d="M10 8l-4 4 4 4M6 12h9"/>',
  power: '<path d="M12 3.5v8"/><path d="M7 6.5a7 7 0 1 0 10 0"/>',
};
export const ICON_NAMES = Object.keys(ICONS);

export const icon = (n, cls = '') =>
  `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ICONS.servidor}</svg>`;

// darker shade of the same hue for the bottom of the icon gradient
function darker(hex, k = 0.6) {
  const n = parseInt(String(hex).slice(1, 7), 16);
  if (isNaN(n)) return hex;
  return '#' + [n >> 16 & 255, n >> 8 & 255, n & 255].map(v => Math.round(v * k).toString(16).padStart(2, '0')).join('');
}

// deterministic colour from the name, so services without `color` still look distinct
const PALETTE = ['#3987e5', '#e5484d', '#30a46c', '#f76b15', '#8e4ec6', '#12a594', '#d6409f', '#ffb224', '#0090ff', '#6e56cf'];
function autoColor(name) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

const isImage = v => /^(https?:)?\/|\.(png|svg|webp|jpe?g|ico)$/i.test(v || '');

export function appIcon(svc) {
  if (isImage(svc.icon)) return `<span class="ico img"><img src="${esc(svc.icon)}" alt="" draggable="false" loading="lazy"></span>`;
  const c = svc.color || autoColor(svc.name);
  const glyph = ICONS[svc.icon] ? icon(svc.icon)
    : `<b class="initial">${esc((svc.name || '?').trim().charAt(0).toUpperCase())}</b>`;
  return `<span class="ico" style="--a:${esc(c)};--a2:${darker(c)}">${glyph}</span>`;
}
