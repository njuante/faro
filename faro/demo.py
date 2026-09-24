"""Demo mode: made-up hosts and services, so anyone can try faro (and take screenshots)
without a single server. `faro demo` uses its own built-in config."""
import math
from collections import deque
import random
import threading
import time

GiB = 2 ** 30
TiB = 2 ** 40

CONFIG = {
    'title': 'Homelab',
    'server': {'port': 8080},
    'auth': {'mode': 'none'},
    'hosts': [
        {'id': 'pve1', 'name': 'pve1', 'description': 'Proxmox · always on', 'transport': 'ssh', 'address': '192.168.1.10'},
        {'id': 'pi', 'name': 'raspberry', 'description': 'Raspberry Pi 5 · Docker', 'transport': 'ssh', 'address': '192.168.1.20'},
    ],
    'services': [
        {'id': 'jellyfin', 'name': 'Jellyfin', 'description': 'Movies and shows', 'url': 'https://jellyfin.example.com',
         'icon': 'play', 'color': '#aa5cc3', 'host': 'pve1', 'guest': 101, 'check': 'none'},
        {'id': 'nextcloud', 'name': 'Nextcloud', 'description': 'Files and photos', 'url': 'https://cloud.example.com',
         'icon': 'nube', 'color': '#0082c9', 'host': 'pve1', 'guest': 102, 'check': 'none'},
        {'id': 'vaultwarden', 'name': 'Vaultwarden', 'description': 'Passwords', 'url': 'https://vault.example.com',
         'icon': 'llave', 'color': '#175ddc', 'host': 'pve1', 'guest': 103, 'check': 'none'},
        {'id': 'grafana', 'name': 'Grafana', 'description': 'Dashboards', 'url': 'https://grafana.example.com',
         'icon': 'grafica', 'color': '#f46800', 'host': 'pve1', 'guest': 104, 'check': 'none'},
        {'id': 'adguard', 'name': 'AdGuard', 'description': 'DNS and ad blocking', 'url': 'https://dns.example.com',
         'icon': 'escudo', 'color': '#68bc71', 'host': 'pi', 'check': 'none'},
        {'id': 'homeassistant', 'name': 'Home Assistant', 'description': 'Home automation',
         'url': 'https://ha.example.com', 'icon': 'casa', 'color': '#18bcf2', 'host': 'pi', 'check': 'none'},
        {'id': 'immich', 'name': 'Immich', 'description': 'Photo backup', 'url': 'https://photos.example.com',
         'icon': 'capas', 'color': '#4250af', 'host': 'pve1', 'guest': 105, 'check': 'none'},
        {'id': 'uptime', 'name': 'Syncthing', 'description': 'File sync', 'url': 'https://sync.example.com',
         'icon': 'sync', 'color': '#0891d1', 'host': 'pi', 'check': 'none'},
    ],
    'disks': [
        {'host': 'pve1', 'serial': 'S4EWNX0R1', 'label': 'System', 'role': 'Proxmox and guest disks'},
        {'host': 'pve1', 'serial': 'WD-WX12A', 'label': 'Data A', 'role': 'ZFS mirror · media and backups'},
        {'host': 'pve1', 'serial': 'WD-WX12B', 'label': 'Data B', 'role': 'ZFS mirror · media and backups'},
        {'host': 'pi', 'serial': 'SD-01', 'label': 'SD card', 'role': 'Raspberry Pi OS'},
    ],
    'guests': {'pve1:106': 'Test VM for Kubernetes', 'pve1:107': 'Windows 11 for games'},
    'plugins': {'ai': {'demo': True}},
}

GUESTS = [  # vmid, kind, name, cpus, maxmem GiB, status
    (101, 'lxc', 'jellyfin', 4, 4, 'running'), (102, 'lxc', 'nextcloud', 2, 4, 'running'),
    (103, 'lxc', 'vaultwarden', 1, 0.5, 'running'), (104, 'lxc', 'grafana', 1, 1, 'running'),
    (105, 'lxc', 'immich', 4, 6, 'running'), (106, 'qemu', 'k3s-lab', 4, 8, 'stopped'),
    (107, 'qemu', 'win11', 8, 16, 'stopped'),
]


def wave(t, period, lo, hi, noise=0.0):
    """Smooth pseudo-random signal between lo and hi: a few sines with unrelated periods."""
    x = (math.sin(2 * math.pi * t / period) + 0.6 * math.sin(2 * math.pi * t / (period * 0.37) + 1.3)
         + 0.35 * math.sin(2 * math.pi * t / (period * 2.9) + 4.1)) / 1.95
    v = lo + (hi - lo) * (0.5 + 0.5 * x)
    return max(0.0, v + random.uniform(-noise, noise))


def bursty(t, base, peak, period):
    """Mostly quiet traffic with the odd burst, like a real network."""
    b = max(0.0, math.sin(2 * math.pi * t / period)) ** 8 + max(0.0, math.sin(2 * math.pi * t / (period * 0.43) + 2)) ** 12
    return base * random.uniform(0.6, 1.4) + peak * b


def pve1(t, up):
    cpu = wave(t, 300, 4, 22, 1.5)
    return {
        'ts': t, 'nic': 'vmbr0', 'cpu_temp': round(38 + cpu * 0.5 + random.uniform(-0.3, 0.3), 1),
        'cpu': {'total': round(cpu, 1), 'cores': [round(min(100, cpu * random.uniform(0.3, 2)), 1) for _ in range(12)]},
        'mem': {'total': 64 * GiB, 'used': int(wave(t, 900, 27, 30) * GiB), 'available': int(35 * GiB),
                'arc': 12 * GiB, 'swap_total': 0, 'swap_used': 0},
        'load': [round(cpu / 12, 2), round(cpu / 14, 2), round(cpu / 16, 2)],
        'uptime': up,
        'net': {'vmbr0': {'rx': bursty(t, 3e5, 9e6, 410), 'tx': bursty(t + 90, 1e5, 2.5e6, 530),
                          'rx_total': 9.1e12, 'tx_total': 2.3e12}},
        'io': {'nvme0n1': {'read': 1.2e6, 'write': 3.4e6, 'busy': 3}, 'sda': {'read': 0, 'write': 5e5, 'busy': 1},
               'sdb': {'read': 0, 'write': 5e5, 'busy': 1}},
        'temps': [{'chip': 'k10temp', 'label': 'Tctl', 'value': round(38 + cpu * 0.5, 1), 'crit': None},
                  {'chip': 'nvme', 'label': 'Composite', 'value': 41.9, 'crit': 84}],
        'gcpu': {101: 0.35, 102: 0.12, 103: 0.01, 104: 0.05, 105: 0.4},
        'host': {'node': 'pve1', 'cpu_model': 'AMD Ryzen 5 5600G with Radeon Graphics', 'threads': 12,
                 'kernel': '6.14.8-2-pve', 'arch': 'x86_64', 'os': 'Debian GNU/Linux 13 (trixie)', 'pve': '9.1.1'},
        'agent': {'version': '1.0.0', 'protocol': 1, 'root': True, 'features': ['lsblk', 'pvesh', 'smartctl', 'zpool']},
        'guests': [{'vmid': v, 'kind': k, 'name': n, 'status': s, 'cpus': c, 'cpu': 0,
                    'mem': int(m * GiB * random.uniform(0.3, 0.6)) if s == 'running' else 0, 'maxmem': int(m * GiB),
                    'disk': int(8 * GiB * random.uniform(0.2, 0.7)), 'maxdisk': 16 * GiB,
                    'uptime': up - 60 if s == 'running' else 0, 'ip': f'192.168.1.{v}',
                    'iface': f'veth{v}i0' if k == 'lxc' else f'tap{v}i0'} for v, k, n, c, m, s in GUESTS],
        'disks': [
            {'name': 'nvme0n1', 'size': 1000 * 10**9, 'model': 'Samsung SSD 980 PRO 1TB', 'serial': 'S4EWNX0R1',
             'tran': 'nvme', 'rota': False, 'mounts': ['/'], 'fstypes': ['LVM2_member', 'ext4'],
             'smart': {'healthy': True, 'temp': 42, 'hours': 11200, 'wear': 3}},
            {'name': 'sda', 'size': 8 * 10**12, 'model': 'WDC WD80EFZZ', 'serial': 'WD-WX12A', 'tran': 'sata',
             'rota': True, 'mounts': [], 'fstypes': ['zfs_member'],
             'smart': {'healthy': True, 'temp': 36, 'hours': 20510, 'realloc': 0, 'pending': 0}},
            {'name': 'sdb', 'size': 8 * 10**12, 'model': 'WDC WD80EFZZ', 'serial': 'WD-WX12B', 'tran': 'sata',
             'rota': True, 'mounts': [], 'fstypes': ['zfs_member'],
             'smart': {'healthy': True, 'temp': 37, 'hours': 20498, 'realloc': 0, 'pending': 0}},
        ],
        'fs': [{'mount': '/', 'dev': '/dev/mapper/pve-root', 'type': 'ext4', 'total': 96 * GiB, 'used': 21 * GiB,
                'avail': 70 * GiB},
               {'mount': '/tank', 'dev': 'tank', 'type': 'zfs', 'total': int(7.1 * TiB), 'used': int(4.2 * TiB),
                'avail': int(2.9 * TiB)}],
        'zfs': {'pools': [{'name': 'tank', 'size': int(7.25 * TiB), 'alloc': int(4.3 * TiB), 'free': int(2.95 * TiB),
                           'frag': '3', 'health': 'ONLINE', 'scan': 'scrub repaired 0B with 0 errors'}],
                'datasets': [{'name': 'tank/media', 'used': int(3.1 * TiB), 'avail': int(2.9 * TiB), 'mount': '/tank/media', 'ratio': '1.01x'},
                             {'name': 'tank/backups', 'used': int(0.8 * TiB), 'avail': int(2.9 * TiB), 'mount': '/tank/backups', 'ratio': '1.34x'},
                             {'name': 'tank/photos', 'used': int(0.3 * TiB), 'avail': int(2.9 * TiB), 'mount': '/tank/photos', 'ratio': '1.02x'}]},
        'storage': [{'storage': 'local-lvm', 'type': 'lvmthin', 'active': 1, 'used': 180 * GiB, 'total': 800 * GiB}],
        'backups': {'backups': {'guests': {str(v): {'ts': t - random.choice((5, 9, 20)) * 3600, 'size': 2 * GiB}
                                           for v, *_ in GUESTS[:5]}}},
        'slow_ts': t,
    }


def pi(t, up):
    cpu = wave(t, 180, 3, 14, 1)
    return {
        'ts': t, 'nic': 'eth0', 'cpu_temp': round(47 + cpu * 0.6, 1),
        'cpu': {'total': round(cpu, 1), 'cores': [round(min(100, cpu * random.uniform(0.5, 1.6)), 1) for _ in range(4)]},
        'mem': {'total': 8 * GiB, 'used': int(wave(t, 600, 2.6, 3.1) * GiB), 'available': 5 * GiB, 'arc': 0,
                'swap_total': 512 * 2**20, 'swap_used': 0},
        'load': [0.4, 0.35, 0.3], 'uptime': up * 0.4,
        'net': {'eth0': {'rx': bursty(t, 4e4, 1.5e6, 350), 'tx': bursty(t + 40, 2e4, 4e5, 290), 'rx_total': 3e11, 'tx_total': 9e10}},
        'io': {'mmcblk0': {'read': 1e4, 'write': 8e4, 'busy': 1}},
        'temps': [{'chip': 'cpu_thermal', 'label': 'cpu_thermal', 'value': round(47 + cpu * 0.6, 1), 'crit': None}],
        'gcpu': {},
        'host': {'node': 'raspberry', 'cpu_model': 'Raspberry Pi 5 Model B Rev 1.0', 'threads': 4,
                 'kernel': '6.12.25+rpt-rpi-2712', 'arch': 'aarch64', 'os': 'Debian GNU/Linux 12 (bookworm)', 'pve': None},
        'agent': {'version': '1.0.0', 'protocol': 1, 'root': True, 'features': ['docker', 'lsblk']},
        'containers': [{'id': 'a1', 'name': 'adguard', 'image': 'adguard/adguardhome', 'state': 'running', 'status': 'Up 3 days'},
                       {'id': 'a2', 'name': 'homeassistant', 'image': 'ghcr.io/home-assistant/home-assistant', 'state': 'running', 'status': 'Up 3 days'},
                       {'id': 'a3', 'name': 'syncthing', 'image': 'syncthing/syncthing', 'state': 'running', 'status': 'Up 3 days'}],
        'disks': [{'name': 'mmcblk0', 'size': 128 * 10**9, 'model': 'SD card', 'serial': 'SD-01', 'tran': None,
                   'rota': False, 'mounts': ['/', '/boot/firmware'], 'fstypes': ['ext4', 'vfat'], 'smart': {}}],
        'fs': [{'mount': '/', 'dev': '/dev/mmcblk0p2', 'type': 'ext4', 'total': 117 * GiB, 'used': 31 * GiB,
                'avail': 80 * GiB}],
        'slow_ts': t,
    }


def start(app):
    hosts = {h['id']: h for h in app.conf['hosts']}
    boot = time.time() - 12 * 86400

    # a day of history so the charts are not empty on first load: one point per minute,
    # then one per second for the last 15 minutes
    now = time.time()
    for i in [*range(86400, 900, -60), *range(900, 0, -1)]:
        for hid, fn in (('pve1', pve1), ('pi', pi)):
            app.hosts.feed(hosts[hid], fn(now - i, now - i - boot))

    def loop():
        while True:
            t = time.time()
            app.hosts.feed(hosts['pve1'], pve1(t, t - boot))
            app.hosts.feed(hosts['pi'], pi(t, t - boot))
            with app.checks.lock:
                for st in app.checks.state.values():
                    up = True
                    ms = round(random.uniform(4, 40), 1)
                    if st['up'] != up:
                        st['since'] = t - 86400 * 3
                    st.update(up=up, code=200, ms=ms, checked=t)
                    if int(t) % 10 == 0:
                        st['history'].append([round(t), 1, ms])
            time.sleep(1)

    with app.checks.lock:          # demo services have check = "none": give them fake state
        for s in app.conf['services']:
            app.checks.state[s['id']] = {'up': None, 'ms': None, 'code': None, 'checked': 0, 'since': now,
                                         'history': deque(
                                             ([round(now - 10 * i), 1, round(random.uniform(4, 40), 1)]
                                              for i in range(90, 0, -1)), maxlen=90)}
    # a few past alerts so the bell has something to show
    with app.alerts.lock:
        app.alerts.log.clear()
        for ago_h, level, title, body in (
                (30, 'bad', 'Immich is down', 'Photo backup · no answer'),
                (29.8, 'good', 'Immich is back up', 'It was down for 12 min.'),
                (6, 'bad', 'Disk Data B is too hot', 'pve1: 61 °C for 5 minutes.'),
                (5.7, 'good', 'Disk Data B has cooled down', 'It was hot for 18 min.'),
                (0.4, 'info', 'Test notification', 'If you can read this, notifications work.')):
            app.alerts.log.append({'ts': now - ago_h * 3600, 'level': level, 'title': title, 'body': body,
                                   'priority': 3, 'url': None, 'key': None})
    threading.Thread(target=loop, daemon=True, name='demo').start()
