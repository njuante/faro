"""Media: what is playing right now and what was added recently, from Jellyfin, Plex and Navidrome.

    [plugins.media]
    jellyfin = { url = "http://192.168.1.21:8096", token = "env:FARO_JELLYFIN", public_url = "https://jellyfin.example.com" }
    plex = { url = "http://192.168.1.22:32400", token = "file:/etc/faro/plex-token" }
    navidrome = { url = "http://192.168.1.23:4533", user = "faro", password = "env:FARO_NAVIDROME" }

Configure any of the three. Artwork goes through faro (and is cached on disk
for a week), so the servers' tokens never reach the browser.
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from .. import BasePlugin, Tool

TEXT = {
    'en': {'tool': ('What is playing right now on Jellyfin, Plex or Navidrome, on which device, and whether it is being '
                    'transcoded. E.g. "is anyone watching something?", "why is the CPU busy?"', 'Checking what is playing…'),
           'nothing': 'Nothing is playing.'},
    'es': {'tool': ('Qué se está reproduciendo ahora en Jellyfin, Plex o Navidrome, en qué aparato y si se está convirtiendo. '
                    'Ej.: "¿alguien está viendo algo?", "¿por qué va alta la CPU?"', 'Mirando qué se reproduce…'),
           'nothing': 'No se está reproduciendo nada.'},
}
IMG_MAX_AGE = 7 * 86400


def get_json(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'faro', **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class Plugin(BasePlugin):
    name = 'media'
    web = 'media.js'

    def __init__(self, app, options):
        super().__init__(app, options)
        self.T = TEXT.get(app.lang, TEXT['en'])
        self.jf = options.get('jellyfin')
        self.plex = options.get('plex')
        self.nd = options.get('navidrome')
        for srv in (self.jf, self.plex, self.nd):
            if srv:
                srv['url'] = srv['url'].rstrip('/')
                srv['public_url'] = (srv.get('public_url') or '').rstrip('/')
        self.demo = bool(options.get('demo'))
        self.img_dir = os.path.join(app.conf['server']['data_dir'], 'img')
        self.lock = threading.Lock()
        self.state = {'playing': [], 'recent': [], 'errors': {}, 'ts': 0}
        self.plex_machine = None

    def start(self):
        if self.demo:
            from .demo import fake_state
            self.state = fake_state()
            return
        threading.Thread(target=self._loop, daemon=True, name='media').start()

    def _loop(self):
        tick = 0
        while True:
            jobs = [('playing', self.now_playing)] + ([('recent', self.recently_added)] if tick % 60 == 0 else [])
            for key, fn in jobs:
                try:
                    value = fn()
                    with self.lock:
                        self.state[key] = value
                        self.state['errors'].pop(key, None)
                except Exception as e:
                    with self.lock:
                        self.state['errors'][key] = f'{type(e).__name__}: {str(e)[:120]}'
            with self.lock:
                self.state['ts'] = time.time()
            tick += 1
            time.sleep(10)

    # ------------------------------------------------------------------ servers

    def _jf_headers(self):
        # recent Jellyfin versions only take the token in Authorization (X-Emby-Token gets a 401)
        return {'Authorization': f'MediaBrowser Token="{self.jf["token"]}"'}

    def _plex(self, path):
        sep = '&' if '?' in path else '?'
        return get_json(f'{self.plex["url"]}{path}{sep}X-Plex-Token={self.plex["token"]}').get('MediaContainer', {})

    def _subsonic(self, method, **extra):
        salt = os.urandom(6).hex()
        token = hashlib.md5((self.nd['password'] + salt).encode()).hexdigest()   # noqa: S324 (the Subsonic API asks for md5)
        q = urllib.parse.urlencode({'u': self.nd['user'], 't': token, 's': salt, 'v': '1.16.1', 'c': 'faro', 'f': 'json',
                                    **extra})
        return f'{self.nd["url"]}/rest/{method}?{q}'

    @staticmethod
    def img(src, key):
        return f'/api/p/media/img?src={src}&key={urllib.parse.quote(str(key), safe="")}' if key else None

    def now_playing(self):
        out = []
        if self.jf:
            for se in get_json(f'{self.jf["url"]}/Sessions?activeWithinSeconds=90', self._jf_headers()):
                m, ps, ti = se.get('NowPlayingItem'), se.get('PlayState') or {}, se.get('TranscodingInfo') or {}
                if not m:
                    continue
                kind = {'Episode': 'episode', 'Audio': 'track'}.get(m.get('Type'), 'movie')
                if kind == 'episode':
                    title, sub, iid = m.get('SeriesName'), f'S{m.get("ParentIndexNumber")} · E{m.get("IndexNumber")} · {m.get("Name")}', m.get('SeriesId')
                elif kind == 'track':
                    title, sub, iid = m.get('Name'), f'{", ".join(m.get("Artists") or [])} · {m.get("Album")}', m.get('AlbumId')
                else:
                    title, sub, iid = m.get('Name'), str(m.get('ProductionYear') or ''), m.get('Id')
                out.append({'source': 'Jellyfin', 'title': title, 'sub': sub, 'kind': kind, 'user': se.get('UserName'),
                            'device': se.get('DeviceName') or se.get('Client'),
                            'state': 'paused' if ps.get('IsPaused') else 'playing',
                            'position': (ps.get('PositionTicks') or 0) // 10000, 'duration': (m.get('RunTimeTicks') or 0) // 10000,
                            'transcoding': bool(ti) and not (ti.get('IsVideoDirect') and ti.get('IsAudioDirect')),
                            'hw': bool(ti.get('HardwareAccelerationType')),
                            'img': self.img('jf', iid or m.get('Id')), 'url': self.jf['public_url'] or None})
        if self.plex:
            for m in self._plex('/status/sessions').get('Metadata', []):
                kind, pl, ts = m.get('type'), m.get('Player') or {}, m.get('TranscodeSession') or {}
                if kind == 'episode':
                    title, sub, thumb = m.get('grandparentTitle'), f'S{m.get("parentIndex")} · E{m.get("index")} · {m.get("title")}', m.get('grandparentThumb')
                elif kind == 'track':
                    title, sub, thumb = m.get('title'), f'{m.get("grandparentTitle")} · {m.get("parentTitle")}', m.get('parentThumb')
                else:
                    title, sub, thumb = m.get('title'), str(m.get('year') or ''), m.get('thumb')
                out.append({'source': 'Plex', 'title': title, 'sub': sub, 'kind': kind,
                            'user': (m.get('User') or {}).get('title'), 'device': pl.get('title') or pl.get('product'),
                            'state': pl.get('state'), 'position': m.get('viewOffset') or 0, 'duration': m.get('duration') or 0,
                            'transcoding': 'transcode' in (ts.get('videoDecision'), ts.get('audioDecision')),
                            'hw': bool(ts.get('transcodeHwEncoding')), 'img': self.img('plex', thumb),
                            'url': self.plex['public_url'] or None})
        if self.nd:
            r = get_json(self._subsonic('getNowPlaying'))['subsonic-response']
            for e in (r.get('nowPlaying') or {}).get('entry', []):
                if (e.get('minutesAgo') or 0) > 15:
                    continue
                out.append({'source': 'Navidrome', 'title': e.get('title'), 'sub': f'{e.get("artist")} · {e.get("album")}',
                            'kind': 'track', 'user': e.get('username'), 'device': e.get('playerName'), 'state': 'playing',
                            'position': None, 'duration': (e.get('duration') or 0) * 1000, 'transcoding': False,
                            'img': self.img('nd', e.get('coverArt')), 'url': self.nd['public_url'] or None})
        return out

    def recently_added(self):
        out = []
        if self.jf:
            users = get_json(f'{self.jf["url"]}/Users', self._jf_headers())
            if users:
                items = get_json(f'{self.jf["url"]}/Users/{users[0]["Id"]}/Items/Latest?Limit=16&IncludeItemTypes=Movie,Series',
                                 self._jf_headers())
                for m in items:
                    out.append({'source': 'Jellyfin', 'title': m.get('SeriesName') or m.get('Name'),
                                'sub': str(m.get('ProductionYear') or ''), 'added': m.get('DateCreated'),
                                'img': self.img('jf', m.get('SeriesId') or m.get('Id')),
                                'url': f'{self.jf["public_url"]}/web/#/details?id={m.get("SeriesId") or m.get("Id")}'
                                       if self.jf['public_url'] else None})
        if self.plex and not out:
            if not self.plex_machine:
                self.plex_machine = self._plex('/identity').get('machineIdentifier')
            for m in self._plex('/library/recentlyAdded?X-Plex-Container-Start=0&X-Plex-Container-Size=16').get('Metadata', []):
                kind = m.get('type')
                title = m.get('parentTitle') if kind == 'season' else m.get('grandparentTitle') if kind == 'episode' else m.get('title')
                key = urllib.parse.quote(f'/library/metadata/{m.get("ratingKey")}', safe='')
                out.append({'source': 'Plex', 'title': title, 'sub': str(m.get('year') or m.get('title') or ''),
                            'added': m.get('addedAt'), 'img': self.img('plex', m.get('thumb') or m.get('parentThumb')),
                            'url': f'{self.plex["public_url"]}/web/index.html#!/server/{self.plex_machine}/details?key={key}'
                                   if self.plex['public_url'] else None})
        return out

    # ------------------------------------------------------------------ artwork

    def artwork_url(self, src, key):
        """Where to fetch an image from. The key is checked so this can't be used to reach arbitrary URLs."""
        if src == 'jf' and self.jf and re.fullmatch(r'[0-9a-f]{32}', key):
            return f'{self.jf["url"]}/Items/{key}/Images/Primary?fillHeight=513&quality=85&api_key={self.jf["token"]}'
        if src == 'plex' and self.plex and re.fullmatch(r'/library/[\w/]+', key):
            return (f'{self.plex["url"]}/photo/:/transcode?width=342&height=513&minSize=1&upscale=1'
                    f'&url={urllib.parse.quote(key, safe="")}&X-Plex-Token={self.plex["token"]}')
        if src == 'nd' and self.nd and re.fullmatch(r'[\w.-]{1,80}', key):
            return self._subsonic('getCoverArt', id=key, size=300)
        return None

    def artwork(self, src, key):
        if self.demo:
            from .demo import poster
            return poster(key), 'image/svg+xml'
        url = self.artwork_url(src, key)
        if not url:
            return None, None
        os.makedirs(self.img_dir, exist_ok=True)
        path = os.path.join(self.img_dir, hashlib.sha256(f'{src}:{key}'.encode()).hexdigest()[:32])
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < IMG_MAX_AGE:
            with open(path, 'rb') as f:
                return f.read(), 'image/jpeg'
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'faro'}), timeout=10) as r:
            data, ctype = r.read(), r.headers.get('Content-Type', 'image/jpeg')
        if ctype.startswith('image/'):
            with open(path, 'wb') as f:
                f.write(data)
        return data, ctype

    # ------------------------------------------------------------------ plugin api

    def routes(self):
        def now(req):
            with self.lock:
                return 200, dict(self.state, errors=dict(self.state['errors']))

        def img(req):
            q = req.query()
            try:
                data, ctype = self.artwork(q.get('src', ''), q.get('key', ''))
            except Exception:
                data, ctype = None, None
            if not data or not (ctype or '').startswith('image/'):
                return 404, {'error': 'no image'}
            req.send(200, data, ctype, [('Cache-Control', 'private, max-age=86400')])
            return None
        return {('GET', '/api/p/media/now'): now, ('GET', '/api/p/media/img'): img}

    def tools(self):
        def playing():
            with self.lock:
                items = list(self.state['playing'])
            if not items:
                return {'result': self.T['nothing']}
            return [{k: x.get(k) for k in ('source', 'title', 'sub', 'user', 'device', 'state', 'transcoding')} |
                    {'progress_pct': round(100 * x['position'] / x['duration']) if x.get('position') and x.get('duration') else None}
                    for x in items]
        return [Tool('now_playing', self.T['tool'][0], playing, step=self.T['tool'][1])]
