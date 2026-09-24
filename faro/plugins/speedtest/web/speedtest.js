// Speed card: ping, download and upload between this device and the server, plus the last results.
const STRINGS = {
  en: { title: 'Speed', down: 'Download', up: 'Upload', ping: 'Ping', run: 'Test', hint: 'Speed between this device and your server',
        pinging: 'Measuring latency…', downloading: 'Measuring download…', uploading: 'Measuring upload…', saving: 'Saving…',
        failed: 'Could not measure. Try again.', last: 'Last test', slow: 'Tight: 1080p video may stutter.',
        ok: 'Fine for 1080p, short for 4K.', good: 'Good speed.', laggy: 'Good speed, but high latency.' },
  es: { title: 'Velocidad', down: 'Bajada', up: 'Subida', ping: 'Ping', run: 'Medir', hint: 'Velocidad entre este aparato y tu servidor',
        pinging: 'Midiendo el retardo…', downloading: 'Midiendo la bajada…', uploading: 'Midiendo la subida…', saving: 'Guardando…',
        failed: 'No he podido medir. Inténtalo otra vez.', last: 'Última medición', slow: 'Va justo: el vídeo 1080p puede cortarse.',
        ok: 'Bien para 1080p, corto para 4K.', good: 'Buena velocidad.', laggy: 'Buena velocidad, aunque el retardo es alto.' },
};
const GAUGE = '<path d="M4.5 18a8.5 8.5 0 1 1 15 0"/><path d="m12 14 4-4"/><circle cx="12" cy="14.5" r="1.4" fill="currentColor"/>';
const API = '/api/p/speedtest/';
const num = v => v >= 100 ? Math.round(v) : v >= 10 ? v.toFixed(1) : v.toFixed(2);

export function init(ctx) {
  const S = STRINGS[ctx.lang] || STRINGS.en, { esc } = ctx;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/p/speedtest/speedtest.css';
  document.head.append(link);
  ctx.addIcon('gauge', GAUGE);
  const card = ctx.addCard('speedtest');
  card.innerHTML = `<header>${ctx.icon('gauge')}${S.title}<span class="extra" data-s="where"></span></header>
    <div class="speed-grid">
      <div class="speed-fig"><b data-s="down">—</b><span>${S.down}</span><small>Mbps</small></div>
      <div class="speed-fig"><b data-s="up">—</b><span>${S.up}</span><small>Mbps</small></div>
      <div class="speed-fig"><b data-s="ping">—</b><span>${S.ping}</span><small>ms</small></div>
    </div>
    <div class="speed-needle"><i data-s="bar"></i></div>
    <div class="speed-foot"><button type="button" data-s="run">${S.run}</button><span data-s="txt">${S.hint}</span></div>
    <div class="speed-hist" data-s="hist"></div>`;
  const $ = k => card.querySelector(`[data-s="${k}"]`);
  let busy = false;

  const verdict = (d, p) => d < 8 ? S.slow : d < 25 ? S.ok : p > 60 ? S.laggy : S.good;
  const show = m => { $('down').textContent = num(m.down); $('up').textContent = num(m.up); $('ping').textContent = Math.round(m.ping); $('where').textContent = m.where || ''; };

  async function history(keepText) {
    try {
      const h = await ctx.api(API + 'history');
      $('hist').innerHTML = h.slice(-6).reverse().map(m => `<span>${new Date(m.ts * 1000).toLocaleString(document.documentElement.lang, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · ↓${num(m.down)} ↑${num(m.up)} · ${Math.round(m.ping)} ms · ${esc(m.where)}</span>`).join('');
      if (h.length && !keepText) { show(h[h.length - 1]); $('txt').textContent = S.last; }
    } catch (e) { /* no history yet */ }
  }

  async function run() {
    if (busy) return;
    busy = true;
    $('run').disabled = true;
    ['down', 'up', 'ping'].forEach(k => { $(k).textContent = '—'; $(k).classList.add('measuring'); });
    const step = (text, pct) => { $('txt').textContent = text; $('bar').style.width = pct + '%'; };
    try {
      // 1) latency: the best of six round trips
      step(S.pinging, 8);
      let ping = 9999, maxMb = 256;
      for (let i = 0; i < 6; i++) {
        const t = performance.now();
        const r = await fetch(API + 'ping?' + Math.random(), { cache: 'no-store' });
        ping = Math.min(ping, performance.now() - t);
        maxMb = (await r.json()).max_mb || maxMb;
      }
      $('ping').textContent = Math.round(ping); $('ping').classList.remove('measuring');

      // 2) download for up to 6 s, counting from the first byte
      step(S.downloading, 25);
      const stop = new AbortController();
      const timer = setTimeout(() => stop.abort(), 6000);
      let bytes = 0, t0 = 0, down = 0;
      try {
        const r = await fetch(API + `down?mb=${maxMb}&` + Math.random(), { cache: 'no-store', signal: stop.signal });
        const reader = r.body.getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          if (!t0) t0 = performance.now();
          bytes += value.length;
          const secs = (performance.now() - t0) / 1000;
          if (secs > 0.3) { down = bytes * 8 / secs / 1e6; $('down').textContent = num(down); step(S.downloading, 25 + Math.min(35, secs * 6)); }
        }
      } catch (e) { /* aborting after 6 s is the normal end */ }
      clearTimeout(timer);
      // a fast link can finish before the first update: always compute the final figure
      if (t0 && bytes) down = bytes * 8 / Math.max((performance.now() - t0) / 1000, 0.001) / 1e6;
      $('down').textContent = num(down);
      $('down').classList.remove('measuring');

      // 3) upload: a size in line with the download speed
      step(S.uploading, 65);
      const mb = Math.max(1, Math.min(96, maxMb, Math.round(down * 0.6)));
      const data = new Uint8Array(mb << 20);
      crypto.getRandomValues(data.subarray(0, 65536));
      for (let i = 65536; i < data.length; i += 65536) data.copyWithin(i, 0, Math.min(65536, data.length - i));
      const t1 = performance.now();
      const res = await fetch(API + 'up', { method: 'POST', body: data, headers: { 'X-Faro': '1' }, cache: 'no-store' });
      const server = await res.json();
      const up = Math.max(data.length * 8 / ((performance.now() - t1) / 1000) / 1e6, server.mbps || 0);
      $('up').textContent = num(up); $('up').classList.remove('measuring');

      step(S.saving, 95);
      const m = await ctx.api(API + 'result', { down, up, ping });
      show(m);
      $('txt').textContent = verdict(down, ping);
      history(true);
    } catch (e) {
      $('txt').textContent = S.failed;
      ['down', 'up', 'ping'].forEach(k => $(k).classList.remove('measuring'));
    }
    $('bar').style.width = '100%';
    setTimeout(() => { $('bar').style.width = '0'; }, 800);
    $('run').disabled = false;
    busy = false;
  }
  $('run').onclick = run;
  history();
}
