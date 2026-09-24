import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from faro.cli import insert_host, set_auth_hash

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'faro.example.toml')
BLOCK = '\n[[hosts]]\nid = "new"\nname = "new"\naddress = "10.0.0.9"\n'


class CliTest(unittest.TestCase):
    def test_insert_host_keeps_hosts_together(self):
        text = insert_host(Path(EXAMPLE).read_text(), BLOCK)
        conf = tomllib.loads(text)
        self.assertEqual([h['id'] for h in conf['hosts']], ['pve1', 'new'])
        # the new block lands before the services section, not at the end of the file
        self.assertLess(text.index('id = "new"'), text.index('# ---------------------------------------------------'
                                                              '--------------- services'))

    def test_insert_host_without_hosts(self):
        text = insert_host('title = "x"\n', BLOCK)
        self.assertEqual(tomllib.loads(text)['hosts'][0]['id'], 'new')

    def test_set_auth_hash(self):
        with tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False) as f:
            f.write(Path(EXAMPLE).read_text())
        try:
            set_auth_hash(f.name, 'pbkdf2_sha256$1$a$b')
            self.assertEqual(tomllib.loads(Path(f.name).read_text())['auth']['password_hash'], 'pbkdf2_sha256$1$a$b')
            with open(f.name, 'w') as g:
                g.write('title = "x"\n')
            set_auth_hash(f.name, 'H')
            self.assertEqual(tomllib.loads(Path(f.name).read_text())['auth']['password_hash'], 'H')
        finally:
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
