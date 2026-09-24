// Media card: what is playing now (with a live progress bar) and what was added recently.
const STRINGS = {
  en: { title: 'Now playing', nothing: 'Nothing is playing right now.', recent: 'Recently added', screens: n => `${n} ${n === 1 ? 'screen' : 'screens'}`,
        transcoding: 'transcoding', gpu: 'GPU', paused: 'paused', left: m => `${m} min left` },
  es: { title: 'Reproduciendo', nothing: 'Ahora no se reproduce nada.', recent: 'Recién añadido', screens: n => `${n} ${n === 1 ? 'pantalla' : 'pantallas'}`,
        transcoding: 'convirtiendo', gpu: 'GPU', paused: 'en pausa', left: m => `quedan ${m} min` },
};
const PLAY = '<path d="M8.5 5.2 18 12l-9.5 6.8z" fill="currentColor" stroke-width="1.2" stroke-linejoin="round"/>';

export function init(ctx) {
  const S = STRINGS[ctx.lang] || STRINGS.en, { esc } = ctx;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/p/media/media.css';
  document.head.append(link);
  ctx.addIcon('play', PLAY);
  const card = ctx.addCard('media');
  card.classList.add('media');
  let data = null, fetchedAt = 0;

  // positions come every 10 s; in between the bar moves on its own
  function position(x) {
    if (x.position == null || !x.duration) return null;
    const extra = x.state === 'playing' ? Date.now() - fetchedAt : 0;
    return Math.min(1, (x.position + extra) / x.duration);
  }

  function paint() {
    if (!data) return;
    const playing = data.playing || [], recent = data.recent || [];
    const tag = (href, cls, inner) => href ? `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener">${inner}</a>` : `<div class="${cls}">${inner}</div>`;
    card.innerHTML = `<header>${ctx.icon('play')}${S.title}<span class="extra">${playing.length ? S.screens(playing.length) : ''}</span></header>
      ${playing.map(x => {
        const p = position(x);
        const left = p != null ? Math.max(0, Math.round((1 - p) * x.duration / 60000)) : null;
        return tag(x.url, 'np', `${x.img ? `<img src="${esc(x.img)}" alt="" loading="lazy">` : ''}
          <div class="tx"><b>${esc(x.title)}</b><span>${esc(x.sub)}</span>
            <div class="meta"><span class="eq ${x.state === 'paused' ? 'paused' : ''}"><s></s><s></s><s></s></span>
              <span>${esc([x.user, x.device].filter(Boolean).join(' · '))}</span>
              <span class="chip">${esc(x.source)}</span>
              ${x.state === 'paused' ? `<span class="chip">${S.paused}</span>` : ''}
              ${x.transcoding ? `<span class="chip warn">${S.transcoding}${x.hw ? ' · ' + S.gpu : ''}</span>` : ''}
              ${left != null ? `<span>${S.left(left)}</span>` : ''}</div>
            ${p != null ? `<div class="bar"><i style="width:${(p * 100).toFixed(1)}%"></i></div>` : ''}</div>`);
      }).join('') || `<p class="empty">${S.nothing}</p>`}
      ${recent.length ? `<h5>${S.recent}</h5><div class="strip-posters">${recent.map(x => tag(x.url, 'poster',
        `<img src="${esc(x.img)}" alt="" loading="lazy"><span>${esc(x.title)}<small>${x.sub ? ' · ' + esc(x.sub) : ''}</small></span>`)).join('')}</div>` : ''}`;
  }

  async function load() {
    try {
      data = await ctx.api('/api/p/media/now');
      fetchedAt = Date.now();
      paint();
    } catch (e) { /* keep the last data */ }
  }
  load();
  setInterval(() => { if (!document.hidden) load(); }, 10000);
  setInterval(() => { if (data?.playing?.some(x => x.state === 'playing')) paint(); }, 5000);
}
