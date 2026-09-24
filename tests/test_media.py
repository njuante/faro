import tempfile
import unittest
from unittest import mock

from faro.app import Faro
from faro.config import normalise
from faro.plugins import media

JF_SESSIONS = [
    {'UserName': 'ana', 'DeviceName': 'TV', 'PlayState': {'IsPaused': False, 'PositionTicks': 6_000_000_000},
     'TranscodingInfo': {'IsVideoDirect': False, 'IsAudioDirect': True, 'HardwareAccelerationType': 'vaapi'},
     'NowPlayingItem': {'Type': 'Episode', 'SeriesName': 'Show', 'ParentIndexNumber': 2, 'IndexNumber': 5,
                        'Name': 'Pilot', 'SeriesId': 'a' * 32, 'RunTimeTicks': 24_000_000_000}},
    {'UserName': 'idle', 'PlayState': {}},          # a session without anything playing
]


class MediaTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        conf = normalise({'server': {'data_dir': self.dir.name}, 'auth': {'mode': 'none'}, 'language': 'en',
                          'plugins': {'media': {'jellyfin': {'url': 'http://jf:8096/', 'token': 'SECRET',
                                                             'public_url': 'https://jf.example.com'},
                                                'plex': {'url': 'http://plex:32400', 'token': 'PLEXSECRET'}}}})
        self.p = Faro(conf).plugin('media')

    def tearDown(self):
        self.dir.cleanup()

    def test_jellyfin_sessions(self):
        def fake(url, headers=None, timeout=8):
            if url.startswith('http://jf:8096/Sessions'):
                self.assertEqual(headers, {'Authorization': 'MediaBrowser Token="SECRET"'})
                return JF_SESSIONS
            return {'MediaContainer': {}}
        with mock.patch.object(media, 'get_json', fake):
            items = self.p.now_playing()
        self.assertEqual(len(items), 1)
        x = items[0]
        self.assertEqual((x['title'], x['sub'], x['device']), ('Show', 'S2 · E5 · Pilot', 'TV'))
        self.assertEqual((x['position'], x['duration']), (600_000, 2_400_000))
        self.assertTrue(x['transcoding'] and x['hw'])
        self.assertEqual(x['img'], f'/api/p/media/img?src=jf&key={"a" * 32}')
        self.assertNotIn('SECRET', repr(items))       # tokens never go to the browser

    def test_artwork_only_for_valid_keys(self):
        self.assertIn('/Items/' + 'b' * 32 + '/Images/Primary', self.p.artwork_url('jf', 'b' * 32))
        self.assertIn('X-Plex-Token=PLEXSECRET', self.p.artwork_url('plex', '/library/metadata/12/thumb/99'))
        for src, key in (('jf', '../../etc/passwd'), ('jf', 'b' * 31), ('plex', 'http://evil/x'),
                         ('plex', '/library/../x'), ('nd', 'x'), ('other', 'x')):
            self.assertIsNone(self.p.artwork_url(src, key), (src, key))

    def test_tool(self):
        tool = self.p.tools()[0]
        self.assertEqual(tool.fn(), {'result': 'Nothing is playing.'})
        self.p.state['playing'] = [{'source': 'Plex', 'title': 'Film', 'sub': '', 'user': 'u', 'device': 'd',
                                    'state': 'playing', 'transcoding': False, 'position': 50, 'duration': 200}]
        self.assertEqual(tool.fn()[0]['progress_pct'], 25)

    def test_demo(self):
        from faro.plugins.media import demo
        self.assertTrue(demo.poster('Sintel').startswith(b'<svg'))
        self.assertIn(b'Sintel', demo.poster('Sintel'))
        self.assertNotIn(b'<script', demo.poster('<script>'))
        self.assertEqual(len(demo.fake_state()['playing']), 2)


if __name__ == '__main__':
    unittest.main()
