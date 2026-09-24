// Tiny canvas line chart with hover tooltip. No dependencies.
import { css, esc, hhmm, hms } from './fmt.js';
import { t } from './i18n.js';

export const charts = [];

export class Chart {
  constructor(box, opts) {
    this.box = box; this.o = opts; this.data = []; this.hover = null; this.span = 900;
    this.cv = document.createElement('canvas');
    this.tip = document.createElement('div'); this.tip.className = 'tip';
    box.append(this.cv, this.tip);
    box.addEventListener('pointermove', e => { this.hover = e.clientX - box.getBoundingClientRect().left; this.draw(); });
    box.addEventListener('pointerleave', () => { this.hover = null; this.draw(); });
    new ResizeObserver(() => this.draw()).observe(box);
    charts.push(this);
  }

  set(data, span) {
    this.span = span;
    const sm = this.o.smooth;
    // turbo boost makes one-second spikes: a short running median reads better
    this.data = sm && span <= 3600 ? data.map((p, i) => {
      const w = data.slice(Math.max(0, i - sm + 1), i + 1).map(q => q.temp).filter(v => v != null).sort((a, b) => a - b);
      return { ...p, temp: w.length ? w[w.length >> 1] : p.temp };
    }) : data;
    this.draw();
  }

  draw() {
    const { cv, box, o } = this, dpr = devicePixelRatio || 1;
    const W = box.clientWidth, H = box.clientHeight;
    if (!W || !H) return;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const padR = 58, padB = 15, pw = W - padR, ph = H - padB - 6;
    const now = this.data.length ? this.data[this.data.length - 1].t : Date.now() / 1000;
    const t0 = now - this.span;
    let max = o.max ?? 0;
    const min = o.min ?? 0;
    if (o.max == null) {
      for (const p of this.data) if (p.t >= t0) for (const s of o.series) { const v = p[s.k]; if (v != null && v > max) max = v; }
      if (o.nice) max = o.nice(max);
      if (o.floor != null) max = Math.max(max, o.floor);
    }
    const X = tt => (tt - t0) / this.span * pw;
    const Y = v => 6 + ph - (v - min) / (max - min || 1) * ph;
    const muted = css('--muted');

    g.font = '11px system-ui, sans-serif'; g.textBaseline = 'middle'; g.lineWidth = 1;
    for (let i = 0; i <= 2; i++) {
      const v = min + (max - min) * i / 2, y = Math.round(Y(v)) + .5;
      g.strokeStyle = i === 0 ? css('--axis') : css('--grid');
      g.beginPath(); g.moveTo(0, y); g.lineTo(pw, y); g.stroke();
      g.fillStyle = muted; g.textAlign = 'left';
      g.fillText(o.fmt(v), pw + 8, y);
    }
    const day = this.span > 3600;
    g.textBaseline = 'alphabetic'; g.fillStyle = muted;
    g.textAlign = 'left'; g.fillText(t(day ? 'ago_24' : 'ago_15'), 0, H - 2);
    g.textAlign = 'center'; g.fillText(t(day ? 'ago_12' : 'ago_7'), pw / 2, H - 2);
    g.textAlign = 'right'; g.fillText(t('now'), pw, H - 2);

    g.lineJoin = 'round'; g.lineCap = 'round';
    const gap = day ? 180 : 5;          // do not draw a line across missing data
    for (const s of o.series) {
      const col = css(s.c);
      if (o.area) {
        g.beginPath(); let started = false, lastX = 0;
        for (const p of this.data) {
          if (p.t < t0 || p[s.k] == null) continue;
          const x = X(p.t);
          if (!started) { g.moveTo(x, Y(min)); started = true; }
          g.lineTo(x, Y(p[s.k])); lastX = x;
        }
        if (started) {
          g.lineTo(lastX, Y(min)); g.closePath();
          const gr = g.createLinearGradient(0, 6, 0, 6 + ph);
          gr.addColorStop(0, col + '5c'); gr.addColorStop(1, col + '00');
          g.fillStyle = gr; g.fill();
        }
      }
      g.beginPath(); let pen = false, prevT = 0;
      for (const p of this.data) {
        const v = p[s.k];
        if (p.t < t0 || v == null) { pen = false; continue; }
        const x = X(p.t), y = Y(v);
        if (pen && p.t - prevT <= gap) g.lineTo(x, y); else g.moveTo(x, y);
        pen = true; prevT = p.t;
      }
      g.strokeStyle = col; g.lineWidth = 2; g.stroke();
    }

    const tip = this.tip;
    if (this.hover == null || this.hover > pw || !this.data.length) { tip.style.display = 'none'; return; }
    const tt = t0 + this.hover / pw * this.span;
    let best = null, bd = Infinity;
    for (const p of this.data) { const d = Math.abs(p.t - tt); if (d < bd) { bd = d; best = p; } }
    if (!best || best.t < t0) { tip.style.display = 'none'; return; }
    const x = Math.round(X(best.t)) + .5;
    g.strokeStyle = css('--axis'); g.lineWidth = 1; g.beginPath(); g.moveTo(x, 6); g.lineTo(x, 6 + ph); g.stroke();
    for (const s of o.series) {
      if (best[s.k] == null) continue;
      g.beginPath(); g.arc(x, Y(best[s.k]), 4, 0, 7);
      g.fillStyle = css(s.c); g.fill(); g.lineWidth = 2; g.strokeStyle = css('--page'); g.stroke();
    }
    tip.innerHTML = `<div class="t">${day ? hhmm(best.t) : hms(best.t)}</div>` + o.series.map(s =>
      `<div class="r"><i style="background:${css(s.c)}"></i>${esc(t(s.label))}<b>${best[s.k] == null ? '–' : o.fmt(best[s.k])}</b></div>`).join('');
    tip.style.display = 'block';
    const tw = tip.offsetWidth;
    tip.style.left = (x + 12 + tw > W ? x - tw - 12 : x + 12) + 'px';
    tip.style.top = '0px';
  }
}
