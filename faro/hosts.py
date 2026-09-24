"""Reads the agents: one long-lived process per host, one JSON line per second."""
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque

LIVE_POINTS = 900      # 15 min at 1 s
DAY_POINTS = 1440      # 24 h at 1 min
SLOW_KEYS = ('disks', 'fs', 'zfs', 'storage', 'backups', 'guests', 'containers', 'slow_ts')
AGENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agent', 'faro-agent.py')


def ssh_base(conf, host):
    ssh_dir = os.path.join(conf['server']['data_dir'], 'ssh')
    return ['ssh', '-i', os.path.join(ssh_dir, 'id_ed25519'),
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + os.path.join(ssh_dir, 'known_hosts'),
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-p', str(host['port']), f'{host["user"]}@{host["address"]}']


def agent_command(conf, host):
    if host['transport'] == 'local':
        return [sys.executable, AGENT]
    # the remote side ignores the command: authorized_keys forces the agent
    return ssh_base(conf, host) + ['faro-agent']


def point(host, d):
    """Reduces a full agent message to one history point."""
    disk_t = [x['smart']['temp'] for x in d.get('disks', []) if (x.get('smart') or {}).get('temp')]
    disk_t += [t['value'] for t in d.get('temps', []) if t['chip'] == 'nvme' and t['label'] == 'Composite']
    nic = d.get('net', {}).get(host['nic'] or d.get('nic') or '', {})
    mem = d.get('mem', {})
    return {'t': round(d['ts']), 'cpu': d['cpu']['total'], 'temp': d.get('cpu_temp'),
            'disk': max(disk_t) if disk_t else None,
            'mem': round(100 * mem['used'] / mem['total'], 1) if mem.get('total') else None,
            'rx': round(nic.get('rx', 0)), 'tx': round(nic.get('tx', 0))}


class Hosts:
    def __init__(self, conf):
        self.conf = conf
        self.lock = threading.Lock()
        self.state = {}                                  # id -> {'data', 'seen', 'error'}
        self.live = {h['id']: deque(maxlen=LIVE_POINTS) for h in conf['hosts']}
        self.day = {h['id']: deque(maxlen=DAY_POINTS) for h in conf['hosts']}
        self.bucket = {h['id']: [] for h in conf['hosts']}
        self.history_path = os.path.join(conf['server']['data_dir'], 'history.json')

    def start(self):
        self._load_history()
        threading.Thread(target=self._save_loop, daemon=True).start()
        for h in self.conf['hosts']:
            threading.Thread(target=self._read_loop, args=(h,), daemon=True, name='host-' + h['id']).start()

    # ------------------------------------------------------------- reading

    def feed(self, host, d):
        """Stores one agent message. Split out so the demo can call it too."""
        hid = host['id']
        pt = point(host, d)
        with self.lock:
            old = self.state.get(hid, {}).get('data') or {}
            for k in SLOW_KEYS:             # slow collectors are missing from the first lines
                if k not in d and k in old:
                    d[k] = old[k]
            self.state[hid] = {'data': d, 'seen': time.time(), 'error': None}
            self.live[hid].append(pt)
            b = self.bucket[hid]
            if b and b[0]['t'] // 60 != pt['t'] // 60:
                self._roll_minute(hid)
            self.bucket[hid].append(pt)

    def _roll_minute(self, hid):
        pts = self.bucket[hid]
        avg = {'t': pts[-1]['t'] // 60 * 60}
        for k in ('cpu', 'temp', 'disk', 'mem', 'rx', 'tx'):
            vals = [p[k] for p in pts if p.get(k) is not None]
            avg[k] = round(sum(vals) / len(vals), 1) if vals else None
        avg['tmax'] = max((p['temp'] for p in pts if p.get('temp') is not None), default=None)
        self.day[hid].append(avg)
        self.bucket[hid] = []

    def _read_loop(self, host):
        backoff = 2
        while True:
            err = ''
            try:
                p = subprocess.Popen(agent_command(self.conf, host), stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, bufsize=1)
                for line in p.stdout:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if 'cpu' in d:
                        self.feed(host, d)
                        backoff = 2
                err = p.stderr.read().strip()[-300:]
                p.wait()
            except Exception as e:
                err = str(e)
            with self.lock:
                self.state.setdefault(host['id'], {})['error'] = err or 'connection closed'
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    # ------------------------------------------------------------- persistence

    def _load_history(self):
        try:
            with open(self.history_path) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        cutoff = time.time() - 86400
        for hid, pts in saved.get('day', {}).items():
            if hid in self.day:
                self.day[hid].extend(p for p in pts if p['t'] > cutoff)

    def _save_loop(self):
        while True:
            time.sleep(300)
            self.save()

    def save(self):
        with self.lock:
            snap = {'day': {h: list(v) for h, v in self.day.items()}}
        tmp = self.history_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(snap, f)
        os.replace(tmp, self.history_path)

    # ------------------------------------------------------------- views

    def seen(self, hid):
        with self.lock:
            return self.state.get(hid, {}).get('seen')

    def data(self, hid):
        with self.lock:
            return self.state.get(hid, {}).get('data')

    def snapshot(self, full):
        now = time.time()
        out = {}
        with self.lock:
            for h in self.conf['hosts']:
                hid = h['id']
                st = self.state.get(hid, {})
                out[hid] = {'data': st.get('data'), 'error': st.get('error'),
                            'online': bool(st.get('seen')) and now - st['seen'] < 6,
                            'last': self.live[hid][-1] if self.live[hid] else None}
                if full:
                    out[hid]['live'] = list(self.live[hid])
                    out[hid]['day'] = list(self.day[hid]) + (
                        [dict(self.bucket[hid][-1], partial=True)] if self.bucket[hid] else [])
        return out
