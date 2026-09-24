import tempfile
import time
import unittest

from faro.auth import MAX_FAILS, Auth, hash_password, verify_password
from faro.config import normalise


class PasswordTest(unittest.TestCase):
    def test_roundtrip(self):
        h = hash_password('correct horse', iterations=1000)
        self.assertTrue(h.startswith('pbkdf2_sha256$1000$'))
        self.assertTrue(verify_password('correct horse', h))
        self.assertFalse(verify_password('wrong', h))

    def test_salted(self):
        self.assertNotEqual(hash_password('x', 1000), hash_password('x', 1000))

    def test_garbage_hash(self):
        for bad in ('', 'nonsense', 'md5$1$a$b', 'pbkdf2_sha256$x$y$z'):
            self.assertFalse(verify_password('x', bad))


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.conf = normalise({'server': {'data_dir': self.dir.name},
                               'auth': {'password_hash': hash_password('pw', 1000)}})
        self.auth = Auth(self.conf)

    def tearDown(self):
        self.dir.cleanup()

    def test_login_logout(self):
        self.assertIsNone(self.auth.login('1.2.3.4', 'nope'))
        token = self.auth.login('1.2.3.4', 'pw')
        self.assertTrue(self.auth.valid(token))
        self.assertFalse(self.auth.valid(token + 'x'))
        self.assertFalse(self.auth.valid(None))
        self.auth.logout(token)
        self.assertFalse(self.auth.valid(token))

    def test_sessions_survive_restart_and_are_stored_hashed(self):
        token = self.auth.login('1.2.3.4', 'pw')
        with open(self.auth.path) as f:
            self.assertNotIn(token, f.read())
        self.assertTrue(Auth(self.conf).valid(token))

    def test_expiry(self):
        token = self.auth.login('1.2.3.4', 'pw')
        for k in self.auth.sessions:
            self.auth.sessions[k] = time.time() - 1
        self.assertFalse(self.auth.valid(token))

    def test_throttle(self):
        for _ in range(MAX_FAILS):
            self.auth.login('9.9.9.9', 'bad')
        self.assertTrue(self.auth.throttled('9.9.9.9'))
        self.assertIsNone(self.auth.login('9.9.9.9', 'pw'))      # even the right password
        self.assertIsNotNone(self.auth.login('8.8.8.8', 'pw'))   # other clients are unaffected

    def test_mode_none(self):
        conf = normalise({'server': {'data_dir': self.dir.name}, 'auth': {'mode': 'none'}})
        self.assertTrue(Auth(conf).valid(None))


if __name__ == '__main__':
    unittest.main()
