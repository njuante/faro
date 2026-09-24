import os
import tempfile
import unittest

from faro.config import ConfigError, load, normalise, public_view


def base(**extra):
    raw = {'hosts': [{'id': 'nas', 'address': '10.0.0.2'}]}
    raw.update(extra)
    return raw


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        c = normalise(base())
        self.assertEqual(c['server']['port'], 8080)
        self.assertEqual(c['auth']['mode'], 'password')
        self.assertEqual(c['hosts'][0]['user'], 'root')
        self.assertEqual(c['backup_max_age']['default'], 26)

    def test_service_ids_and_default_check(self):
        c = normalise(base(services=[{'name': 'Home Assistant', 'url': 'http://10.0.0.3:8123'},
                                     {'name': 'No URL'}]))
        ha, other = c['services']
        self.assertEqual(ha['id'], 'home-assistant')
        self.assertEqual(ha['check'], 'http')
        self.assertEqual(ha['target'], 'http://10.0.0.3:8123')
        self.assertEqual(other['check'], 'none')

    def test_duplicate_ids(self):
        with self.assertRaisesRegex(ConfigError, 'share the id'):
            normalise(base(services=[{'name': 'A'}, {'name': 'a'}]))

    def test_unknown_host(self):
        with self.assertRaisesRegex(ConfigError, 'unknown host'):
            normalise(base(services=[{'name': 'x', 'url': 'http://x', 'host': 'nope'}]))

    def test_tcp_needs_target(self):
        with self.assertRaisesRegex(ConfigError, 'needs a target'):
            normalise(base(services=[{'name': 'x', 'check': 'tcp'}]))

    def test_ssh_host_needs_address(self):
        with self.assertRaisesRegex(ConfigError, 'missing address'):
            normalise({'hosts': [{'id': 'a'}]})
        normalise({'hosts': [{'id': 'a', 'transport': 'local'}]})

    def test_api_token_format(self):
        with self.assertRaisesRegex(ConfigError, 'api_token'):
            normalise({'hosts': [{'id': 'a', 'address': 'x', 'api_token': 'nonsense'}]})
        c = normalise({'hosts': [{'id': 'a', 'address': 'x', 'api_token': 'faro@pve!faro=abc'}]})
        self.assertEqual(c['hosts'][0]['api_url'], 'https://x:8006')

    def test_secrets_from_env_and_file(self):
        os.environ['FARO_TEST_SECRET'] = 's3cret'
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write('from-file\n')
        try:
            c = normalise(base(notify={'ntfy': {'url': 'https://ntfy.sh', 'token': 'env:FARO_TEST_SECRET'}},
                               auth={'password_hash': 'file:' + f.name}))
            self.assertEqual(c['notify']['ntfy']['token'], 's3cret')
            self.assertEqual(c['auth']['password_hash'], 'from-file')
        finally:
            os.unlink(f.name)
        with self.assertRaisesRegex(ConfigError, 'FARO_MISSING'):
            normalise(base(auth={'password_hash': 'env:FARO_MISSING'}))

    def test_public_view_has_no_secrets(self):
        c = normalise({'hosts': [{'id': 'a', 'address': 'x', 'api_token': 'faro@pve!faro=TOPSECRET'}],
                       'auth': {'password_hash': 'HASH'}, 'notify': {'ntfy': {'url': 'https://n', 'token': 'TOKEN'}}})
        text = repr(public_view(c))
        for secret in ('TOPSECRET', 'HASH', 'TOKEN'):
            self.assertNotIn(secret, text)
        self.assertTrue(public_view(c)['hosts'][0]['actions'])

    def test_example_file_is_valid(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        c = load(os.path.join(here, 'faro.example.toml'))
        self.assertEqual(c['hosts'][0]['id'], 'pve1')

    def test_bad_toml(self):
        with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False) as f:
            f.write('title = \n')
        try:
            with self.assertRaises(ConfigError):
                load(f.name)
        finally:
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
