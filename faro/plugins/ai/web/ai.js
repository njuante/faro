// Assistant card: questions about the homelab, answered by a local model and streamed word by word.
const STRINGS = {
  en: {
    title: 'Assistant', placeholder: 'Ask about your servers…', send: 'Send', new: 'New', sleep: 'Sleep', wake: 'Wake',
    ready: 'ready', idle: 'asleep', offline: 'offline', no_answer: 'No answer arrived.', cannot: 'Cannot reach the assistant.',
    looked: 'looked at', suggestions: ['Is everything OK?', 'What is using the CPU?', 'When was the last backup?',
      'How are the disks?', 'Which VMs are running?', 'What broke recently?'],
  },
  es: {
    title: 'Asistente', placeholder: 'Pregunta por tus servidores…', send: 'Enviar', new: 'Nueva', sleep: 'Dormir', wake: 'Despertar',
    ready: 'listo', idle: 'en reposo', offline: 'sin conexión', no_answer: 'No ha llegado respuesta.', cannot: 'No puedo conectar con el asistente.',
    looked: 'ha mirado', suggestions: ['¿Va todo bien?', '¿Qué gasta CPU?', '¿Cuándo fue la última copia?',
      '¿Cómo están los discos?', '¿Qué máquinas están encendidas?', '¿Qué ha fallado últimamente?'],
  },
};
const SPARKLE = '<path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.5l-1.9-5.7L4.5 10.9 10.1 9z"/><path d="M19 3v3M17.5 4.5h3M5 17.5v3M3.5 19h3"/>';
const ARROW = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"/><path d="m5.5 11.5 6.5-6.5 6.5 6.5"/></svg>';

export function init(ctx) {
  const S = STRINGS[ctx.lang] || STRINGS.en;
  const { esc } = ctx;
  ctx.addIcon('sparkle', SPARKLE);
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/p/ai/ai.css';
  document.head.append(link);

  const card = ctx.addCard('ai');
  card.classList.add('ai');
  card.innerHTML = `<header>${ctx.icon('sparkle')}${S.title}<span class="extra" data-a="status"></span></header>
    <div class="ai-conv" data-a="conv" aria-live="polite"></div>
    <div class="ai-sug" data-a="sug">${S.suggestions.map(q => `<button type="button">${esc(q)}</button>`).join('')}</div>
    <form class="ai-form" data-a="form" autocomplete="off">
      <input type="text" maxlength="400" enterkeyhint="send" placeholder="${S.placeholder}" aria-label="${S.placeholder}">
      <button type="submit" aria-label="${S.send}" disabled>${ARROW}</button>
    </form>`;
  const $ = k => card.querySelector(`[data-a="${k}"]`);
  const input = card.querySelector('input'), sendBtn = card.querySelector('form button');

  // the conversation survives reloads within the tab
  let conv = [];
  try { conv = JSON.parse(sessionStorage.getItem('faro-ai') || '[]'); } catch (e) { conv = []; }
  const save = () => { try { sessionStorage.setItem('faro-ai', JSON.stringify(conv.slice(-12))); } catch (e) { /* ignore */ } };
  let busy = false, status = { ok: null, loaded: false };

  // tiny, safe markdown: everything is escaped first
  function md(text) {
    const lines = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>').split('\n');
    let html = '', list = false;
    for (const l of lines) {
      const m = l.match(/^\s*(?:[-•*]|\d+[.)])\s+(.*)/);
      if (m) { if (!list) { html += '<ul>'; list = true; } html += `<li>${m[1]}</li>`; continue; }
      if (list) { html += '</ul>'; list = false; }
      if (l.trim()) html += `<p>${l}</p>`;
    }
    return html + (list ? '</ul>' : '');
  }

  function paint(live) {
    const box = $('conv');
    box.innerHTML = conv.map((m, i) => {
      if (m.role === 'user') return `<div class="ai-msg me">${esc(m.text)}</div>`;
      if (m.error) return `<div class="ai-msg bot error">${esc(m.error)}</div>`;
      const last = live && i === conv.length - 1;
      if (last && !m.text) return `<div class="ai-msg bot"><span class="ai-thinking"><s></s><s></s><s></s></span>${m.step ? `<small class="ai-step">${esc(m.step)}</small>` : ''}</div>`;
      const meta = !last && m.secs ? `<small>${m.tools?.length ? `🔎 ${S.looked} ${esc(m.tools.join(', '))} · ` : ''}${m.secs} s</small>` : '';
      return `<div class="ai-msg bot ${last ? 'ai-cursor' : ''}">${md(m.text)}${meta}</div>`;
    }).join('');
    box.scrollTop = box.scrollHeight;
    $('sug').hidden = conv.length > 0;
    const word = status.ok === false ? S.offline : status.loaded ? S.ready : status.ok ? S.idle : '';
    const dot = status.ok === false ? 'bad' : status.loaded ? 'ok' : status.ok ? 'idle' : '';
    $('status').innerHTML = `<span class="dot ${dot}"></span>${word}` +
      (conv.length && !busy ? `<button type="button" data-a="new">${S.new}</button>` : '') +
      (status.ok && !busy ? `<button type="button" data-a="${status.loaded ? 'sleep' : 'wake'}">${status.loaded ? S.sleep : S.wake}</button>` : '');
    sendBtn.disabled = busy || !input.value.trim();
  }

  async function refreshStatus(warm) {
    try { status = await ctx.api('/api/p/ai/status' + (warm ? '?warm=1' : '')); } catch (e) { status = { ok: false }; }
    paint();
  }

  async function ask(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    input.value = '';
    conv.push({ role: 'user', text });
    const reply = { role: 'assistant', text: '' };
    conv.push(reply);
    busy = true; paint(true);
    const t0 = Date.now();
    let frame = 0;
    try {
      const res = await fetch('/api/p/ai/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Faro': '1' },
        body: JSON.stringify({ messages: conv.slice(0, -1).filter(m => !m.error).slice(-7) }),
      });
      const reader = res.body.getReader(), dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let k;
        while ((k = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, k); buf = buf.slice(k + 2);
          if (!line.startsWith('data: ')) continue;
          const d = JSON.parse(line.slice(6));
          if (d.t) { reply.text += d.t; reply.step = ''; }
          if (d.step) reply.step = d.step;
          if (d.error) reply.error = d.error;
          if (d.done) { reply.tps = d.tps; reply.tools = d.tools; }
        }
        if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); });
      }
      if (!reply.text && !reply.error) reply.error = S.no_answer;
    } catch (e) {
      reply.error = S.cannot;
    }
    cancelAnimationFrame(frame);        // a late repaint would bring the cursor back
    reply.secs = Math.round((Date.now() - t0) / 100) / 10;
    busy = false; save();
    paint();
    refreshStatus();
  }

  $('sug').onclick = e => { const b = e.target.closest('button'); if (b) ask(b.textContent); };
  $('form').onsubmit = e => { e.preventDefault(); ask(input.value); };
  input.oninput = () => { sendBtn.disabled = busy || !input.value.trim(); };
  input.onfocus = () => refreshStatus(true);          // start loading the model while the question is typed
  $('status').onclick = async e => {
    const a = e.target.dataset.a;
    if (a === 'new') { conv = []; save(); paint(); }
    if (a === 'sleep') { await ctx.api('/api/p/ai/sleep', {}); setTimeout(refreshStatus, 1500); }
    if (a === 'wake') { await refreshStatus(true); setTimeout(refreshStatus, 9000); }
  };
  paint();
  refreshStatus();
}
