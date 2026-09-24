"""Made-up media for demo mode: Blender's open movies and drawn posters."""
import time
import zlib
from html import escape

MOVIES = [('Big Buck Bunny', 2008), ('Sintel', 2010), ('Tears of Steel', 2012), ('Elephants Dream', 2006),
          ('Spring', 2019), ('Cosmos Laundromat', 2015), ('Agent 327', 2017), ('Caminandes', 2013), ('Sprite Fright', 2021)]
COLORS = [('#e5484d', '#6e1a1d'), ('#3987e5', '#12325c'), ('#30a46c', '#113b27'), ('#f76b15', '#5e2606'),
          ('#8e4ec6', '#34184d'), ('#12a594', '#07403a'), ('#ffb224', '#5c3b00'), ('#d6409f', '#4d0f35')]


def poster(key):
    """An SVG poster: gradient, a big circle and the title. Deterministic per key."""
    title = str(key)
    a, b = COLORS[zlib.crc32(title.encode()) % len(COLORS)]
    words, lines = title.split(), []
    for w in words:
        if lines and len(lines[-1]) + len(w) < 12:
            lines[-1] += ' ' + w
        else:
            lines.append(w)
    text = ''.join(f'<text x="24" y="{400 + i * 40}" font-family="Georgia,serif" font-size="36" fill="#fff">{escape(ln)}</text>'
                   for i, ln in enumerate(lines))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="342" height="513" viewBox="0 0 342 513">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/>'
           f'<stop offset="1" stop-color="{b}"/></linearGradient></defs><rect width="342" height="513" fill="url(#g)"/>'
           f'<circle cx="250" cy="150" r="110" fill="#fff" opacity=".13"/><circle cx="250" cy="150" r="60" fill="#fff" opacity=".18"/>'
           f'{text}</svg>')
    return svg.encode()


def fake_state():
    img = lambda t: f'/api/p/media/img?src=demo&key={t.replace(" ", "%20")}'   # noqa: E731
    now = time.time()
    return {
        'playing': [
            {'source': 'Jellyfin', 'title': 'Sintel', 'sub': '2010', 'kind': 'movie', 'user': 'ana', 'device': 'Living room TV',
             'state': 'playing', 'position': 312000, 'duration': 888000, 'transcoding': False, 'img': img('Sintel'), 'url': None},
            {'source': 'Plex', 'title': 'Tears of Steel', 'sub': '2012', 'kind': 'movie', 'user': 'leo', 'device': 'iPad',
             'state': 'paused', 'position': 420000, 'duration': 734000, 'transcoding': True, 'hw': True,
             'img': img('Tears of Steel'), 'url': None},
        ],
        'recent': [{'source': 'Jellyfin', 'title': t, 'sub': str(y), 'added': None, 'img': img(t), 'url': None}
                   for t, y in MOVIES],
        'errors': {}, 'ts': now,
    }
