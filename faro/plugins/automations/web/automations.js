// Automations card: what faro does by itself, a switch for each rule and what it did lately.
const STRINGS = {
  en: { title: 'Automatic', recent: 'Lately', nothing: 'Nothing done yet.' },
  es: { title: 'Automático', recent: 'Últimamente', nothing: 'Aún no ha hecho nada.' },
};
const GEAR = '<path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2"/><circle cx="12" cy="12" r="3.2"/>';

export function init(ctx) {
  const S = STRINGS[ctx.lang] || STRINGS.en, { esc } = ctx;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/p/automations/automations.css';
  document.head.append(link);
  ctx.addIcon('gear', GEAR);
  const card = ctx.addCard('automations');
  const report = (ctx.app.S.actions || []).find(a => a.id === 'report.now');
  let data = null;

  function when(ts) {
    const d = new Date(ts * 1000), today = new Date().toDateString() === d.toDateString();
    return d.toLocaleString(document.documentElement.lang, today ? { hour: '2-digit', minute: '2-digit' }
      : { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  function paint() {
    if (!data) return;
    card.innerHTML = `<header>${ctx.icon('gear')}${S.title}</header>
      ${data.rules.map(r => `<div class="rule"><div class="tx"><b>${esc(r.name)}</b><span>${esc(r.text)}</span></div>
        <button class="switch ${r.on ? 'on' : ''}" type="button" role="switch" aria-checked="${r.on}" aria-label="${esc(r.name)}" data-rule="${esc(r.id)}"></button></div>`).join('')}
      <h5 class="sub-h" style="margin:6px 0 0">${S.recent}</h5>
      <div class="auto-log">${data.log.slice(0, 5).map(l => `<div class="${l.ok ? '' : 'bad'}"><time>${when(l.ts)}</time><span title="${esc(l.text)}">${esc(l.text)}</span></div>`).join('')
        || `<div><span>${S.nothing}</span></div>`}</div>
      ${report ? `<div class="auto-foot"><button type="button" data-report>${esc(report.label)}</button></div>` : ''}`;
  }

  card.addEventListener('click', async e => {
    const sw = e.target.closest('[data-rule]');
    if (sw) {
      const on = !sw.classList.contains('on');
      sw.classList.toggle('on', on);
      const r = await ctx.api('/api/p/automations/toggle', { id: sw.dataset.rule, on });
      data.rules = r.rules;
      paint();
    }
    if (e.target.closest('[data-report]')) {
      const r = await ctx.api('/api/action', { id: 'report.now', params: {} });
      ctx.toast(r.text, !r.ok);
      setTimeout(load, 4000);
    }
  });

  async function load() {
    try { data = await ctx.api('/api/p/automations'); paint(); } catch (e) { /* keep the last one */ }
  }
  load();
  setInterval(() => { if (!document.hidden) load(); }, 60000);
}
