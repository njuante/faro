import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

AGENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agent', 'faro-agent.py')
spec = importlib.util.spec_from_file_location('faro_agent', AGENT)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

STORAGE_CFG = """dir: local
\tpath /var/lib/vz
\tcontent iso,vztmpl,backup

lvmthin: local-lvm
\tthinpool data
\tcontent rootdir,images

dir: usb
\tpath /mnt/usb
\tcontent backup
\tis_mountpoint yes

dir: isos
\tpath /mnt/isos
\tcontent iso
"""


class AgentTest(unittest.TestCase):
    def test_backup_dirs_from_storage_cfg(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(STORAGE_CFG)
        real = agent.read
        agent.read = lambda p, d='': real(f.name) if p == '/etc/pve/storage.cfg' else real(p, d)
        try:
            self.assertEqual(agent.backup_dirs(), [('local', '/var/lib/vz'), ('usb', '/mnt/usb')])
        finally:
            agent.read = real
            os.unlink(f.name)

    def test_cpu_temp_picks_the_package(self):
        ts = [{'chip': 'acpitz', 'label': 'acpitz', 'value': 27.8},
              {'chip': 'coretemp', 'label': 'Core 0', 'value': 40.0},
              {'chip': 'coretemp', 'label': 'Package id 0', 'value': 44.0}]
        self.assertEqual(agent.cpu_temp(ts), 44.0)
        self.assertEqual(agent.cpu_temp([{'chip': 'k10temp', 'label': 'Tctl', 'value': 51.5}]), 51.5)
        self.assertEqual(agent.cpu_temp([{'chip': 'cpu_thermal', 'label': 'cpu_thermal', 'value': 48.2}]), 48.2)
        self.assertIsNone(agent.cpu_temp([]))

    def test_disk_regex(self):
        for name in ('sda', 'nvme0n1', 'vdb', 'mmcblk0', 'xvda'):
            self.assertTrue(agent.DISK_RE.fullmatch(name), name)
        for name in ('sda1', 'nvme0n1p2', 'loop0', 'dm-0', 'zd16'):
            self.assertFalse(agent.DISK_RE.fullmatch(name), name)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'reads /proc')
    def test_runs_once_and_prints_json(self):
        out = subprocess.run([sys.executable, AGENT, '--once'], capture_output=True, text=True, timeout=120)
        d = json.loads(out.stdout.splitlines()[0])
        for key in ('host', 'agent', 'cpu', 'mem', 'net', 'load', 'uptime', 'fs'):
            self.assertIn(key, d)
        self.assertEqual(d['agent']['protocol'], 1)
        self.assertGreater(d['mem']['total'], 0)


if __name__ == '__main__':
    unittest.main()
