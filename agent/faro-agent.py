#!/usr/bin/env python3
"""faro-agent: host metrics as JSON lines on stdout, one per second.

The agent never opens a port. The faro server starts it over SSH with a
restricted key (a forced command in authorized_keys), reads its stdout and
closes the connection when it is done. It only reads; standard library only;
Python 3.7+.

Every collector is optional and detected at runtime, so the same file works on
a Raspberry Pi, a VPS or a Proxmox node:

  always     cpu, memory, network, disk I/O, temperatures, load, filesystems
  Proxmox    guests (LXC/QEMU), storages, vzdump backups   (pvesh)
  ZFS        pools and datasets                            (zpool, zfs)
  SMART      disk health                                   (smartctl, needs root)
  Docker     containers                                    (docker)
"""
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

VERSION = '1.0.0'
PROTOCOL = 1

state = {}
lock = threading.Lock()


def sh(cmd, timeout=20):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True, timeout=timeout).stdout
    except Exception:
        return ''


def read(path, default=''):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


def put(key, value):
    with lock:
        state[key] = value


HAS = {tool: bool(shutil.which(tool)) for tool in ('pvesh', 'zpool', 'smartctl', 'docker', 'lsblk')}
IS_ROOT = os.geteuid() == 0
NODE = socket.gethostname()


def container_type():
    """'lxc', 'docker', ... or None. Inside a container the disks listed are the host's, not ours."""
    marker = read('/run/systemd/container')      # readable without root, unlike /proc/1/environ
    if marker:
        return marker
    env = read('/proc/1/environ').split('\0')
    for item in env:
        if item.startswith('container='):
            return item.split('=', 1)[1] or 'container'
    if os.path.exists('/.dockerenv'):
        return 'docker'
    return None


CONTAINER = container_type()


# ---------------------------------------------------------------- fast (1 s)

def cpu_times():
    out = {}
    for line in read('/proc/stat').splitlines():
        if line.startswith('cpu'):
            p = line.split()
            v = list(map(int, p[1:9]))
            out[p[0]] = (sum(v), v[3] + v[4])      # total, idle + iowait
    return out


def net_counters():
    out = {}
    for line in read('/proc/net/dev').splitlines()[2:]:
        name, data = line.split(':', 1)
        f = data.split()
        out[name.strip()] = (int(f[0]), int(f[8]))
    return out


DISK_RE = re.compile(r'sd[a-z]+|hd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+')


def disk_counters():
    out = {}
    for line in read('/proc/diskstats').splitlines():
        f = line.split()
        if DISK_RE.fullmatch(f[2]):
            # 512-byte sectors read/written, ms spent doing I/O
            out[f[2]] = (int(f[5]) * 512, int(f[9]) * 512, int(f[12]))
    return out


def default_nic():
    """Interface of the default route: the one worth charting."""
    for line in read('/proc/net/route').splitlines()[1:]:
        f = line.split()
        if len(f) > 2 and f[1] == '00000000':
            return f[0]
    return None


def temps():
    res = []
    for hw in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
        chip = read(hw + '/name')
        if chip.startswith('iwlwifi'):
            continue
        for inp in sorted(glob.glob(hw + '/temp*_input'), key=lambda s: int(re.search(r'temp(\d+)', s).group(1))):
            base = inp[:-6]
            try:
                val = int(read(inp)) / 1000
            except ValueError:
                continue
            crit = read(base + '_crit') or read(base + '_max')
            res.append({'chip': chip, 'label': read(base + '_label') or chip, 'value': round(val, 1),
                        'crit': round(int(crit) / 1000) if crit.isdigit() and int(crit) > 0 else None})
    if not res:     # Raspberry Pi and some ARM boards only expose thermal zones
        for z in sorted(glob.glob('/sys/class/thermal/thermal_zone*')):
            v = read(z + '/temp')
            if v.lstrip('-').isdigit():
                res.append({'chip': read(z + '/type') or 'thermal', 'label': read(z + '/type') or 'cpu',
                            'value': round(int(v) / 1000, 1), 'crit': None})
    return res


def cpu_temp(ts):
    """Best guess at 'the CPU temperature' across Intel, AMD and ARM."""
    for want in (('coretemp', 'Package'), ('k10temp', 'Tctl'), ('k10temp', 'Tdie'), ('zenpower', 'Tdie'),
                 ('cpu_thermal', ''), ('cpu-thermal', ''), ('x86_pkg_temp', ''), ('acpitz', '')):
        for t in ts:
            if t['chip'] == want[0] and t['label'].startswith(want[1]):
                return t['value']
    return None


def meminfo():
    m = {}
    for line in read('/proc/meminfo').splitlines():
        k, v = line.split(':')
        m[k] = int(v.split()[0]) * 1024
    arc = 0
    for line in read('/proc/spl/kstat/zfs/arcstats').splitlines():
        if line.startswith('size '):
            arc = int(line.split()[2])
    avail = m.get('MemAvailable', m.get('MemFree', 0))
    return {'total': m['MemTotal'], 'available': avail, 'used': m['MemTotal'] - avail, 'arc': arc,
            'swap_total': m.get('SwapTotal', 0), 'swap_used': m.get('SwapTotal', 0) - m.get('SwapFree', 0)}


def guest_cpu_usage():
    # pvesh reports cpu=0 for containers on PVE 9: read the cgroup instead (µs of CPU)
    out = {}
    for path, rx in (('/sys/fs/cgroup/lxc/*/cpu.stat', r'/lxc/(\d+)/'),
                     ('/sys/fs/cgroup/qemu.slice/*.scope/cpu.stat', r'/(\d+)\.scope/')):
        for f in glob.glob(path):
            m = re.search(rx, f)
            line = read(f).split('\n', 1)[0].split()
            if m and len(line) == 2 and line[0] == 'usage_usec':
                out[int(m.group(1))] = int(line[1])
    return out


def fast_loop():
    pc, pn, pd, pg, pt = cpu_times(), net_counters(), disk_counters(), guest_cpu_usage(), time.time()
    while True:
        time.sleep(1)
        c, n, d, gu, t = cpu_times(), net_counters(), disk_counters(), guest_cpu_usage(), time.time()
        dt = t - pt
        cpu = {}
        for k, (tot, idle) in c.items():
            if k in pc:
                dtot = tot - pc[k][0]
                cpu[k] = round(100 * (1 - (idle - pc[k][1]) / dtot), 1) if dtot else 0
        net = {}
        for k, (rx, tx) in n.items():
            if k in pn and k != 'lo':
                net[k] = {'rx': max(0, (rx - pn[k][0]) / dt), 'tx': max(0, (tx - pn[k][1]) / dt),
                          'rx_total': rx, 'tx_total': tx}
        io = {}
        for k, (r, w, busy) in d.items():
            if k in pd:
                io[k] = {'read': max(0, (r - pd[k][0]) / dt), 'write': max(0, (w - pd[k][1]) / dt),
                         'busy': min(100, round((busy - pd[k][2]) / (dt * 10), 1))}
        gcpu = {k: round((v - pg[k]) / 1e6 / dt, 3) for k, v in gu.items() if k in pg}   # cores in use
        ts = temps()
        with lock:
            state.update({
                'ts': t,
                'cpu': {'total': cpu.pop('cpu', 0), 'cores': [cpu[k] for k in sorted(cpu, key=lambda s: int(s[3:]))]},
                'net': net, 'io': io, 'gcpu': gcpu, 'temps': ts, 'cpu_temp': cpu_temp(ts), 'mem': meminfo(),
                'load': [float(x) for x in read('/proc/loadavg').split()[:3]],
                'uptime': float(read('/proc/uptime').split()[0]),
                'nic': default_nic(),
            })
        pc, pn, pd, pg, pt = c, n, d, gu, t


# ---------------------------------------------------------------- medium (5 s)

def guest_ip(kind, vmid):
    conf = read('/etc/pve/%s/%s.conf' % ('lxc' if kind == 'lxc' else 'qemu-server', vmid))
    m = re.search(r'ip=([\d.]+)', conf)
    return m.group(1) if m else None


def proxmox_guests():
    out = []
    for kind in ('lxc', 'qemu'):
        try:
            rows = json.loads(sh(['pvesh', 'get', '/nodes/%s/%s' % (NODE, kind), '--output-format', 'json']) or '[]')
        except ValueError:
            rows = []
        for g in rows:
            vmid = int(g['vmid'])
            out.append({'vmid': vmid, 'kind': kind, 'name': g.get('name'), 'status': g.get('status'),
                        'cpu': round(100 * float(g.get('cpu') or 0), 1), 'cpus': g.get('cpus'),
                        'mem': g.get('mem', 0), 'maxmem': g.get('maxmem', 0),
                        'disk': g.get('disk', 0), 'maxdisk': g.get('maxdisk', 0),
                        'uptime': g.get('uptime', 0), 'ip': guest_ip(kind, vmid),
                        'iface': ('veth%si0' if kind == 'lxc' else 'tap%si0') % vmid})
    return sorted(out, key=lambda g: g['vmid'])


def docker_containers():
    out = []
    for line in sh(['docker', 'ps', '-a', '--no-trunc', '--format', '{{json .}}'], timeout=10).splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        out.append({'id': c.get('ID', '')[:12], 'name': c.get('Names'), 'image': c.get('Image'),
                    'state': c.get('State'), 'status': c.get('Status'), 'ports': c.get('Ports')})
    return sorted(out, key=lambda c: c['name'] or '')


def guests_loop():
    while True:
        if HAS['pvesh']:
            put('guests', proxmox_guests())
        if HAS['docker']:
            put('containers', docker_containers())
        time.sleep(5)


# ---------------------------------------------------------------- slow (60 s)

SSD = set()   # no moving parts: no need to respect standby


def smart(dev):
    j, standby = {}, False
    for extra in ([], ['-d', 'sat']):
        args = ['smartctl', '-j'] + extra + ([] if dev in SSD else ['-n', 'standby']) + ['-a', dev]
        try:
            j = json.loads(sh(args) or '{}')
        except ValueError:
            j = {}
        msgs = json.dumps(j.get('smartctl', {}).get('messages', []))
        if 'SLEEP' in msgs and extra:
            # some USB bridges always report SLEEP: read without -n
            try:
                j = json.loads(sh(['smartctl', '-j'] + extra + ['-a', dev]) or '{}')
            except ValueError:
                j = {}
        elif 'STANDBY' in msgs:
            standby = True
            break
        if j.get('smart_status') or j.get('temperature'):
            break
    if j.get('rotation_rate') == 0:
        SSD.add(dev)
    attrs = {a['id']: a['raw']['value'] for a in j.get('ata_smart_attributes', {}).get('table', [])}
    nv = j.get('nvme_smart_health_information_log', {})
    return {
        'healthy': j.get('smart_status', {}).get('passed'),
        'temp': j.get('temperature', {}).get('current'),
        'hours': j.get('power_on_time', {}).get('hours'),
        'realloc': attrs.get(5), 'pending': attrs.get(197),
        'wear': nv.get('percentage_used'), 'standby': standby,
    }


def disks():
    try:
        tree = json.loads(sh(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,MODEL,SERIAL,TRAN,TYPE,MOUNTPOINT,FSTYPE,ROTA']))
    except ValueError:
        return []
    out = []
    for d in tree.get('blockdevices', []):
        if d['type'] != 'disk' or d['name'].startswith(('zd', 'loop', 'ram')):
            continue
        mounts, fstypes = [], set()

        def walk(n):
            if n.get('mountpoint'):
                mounts.append(n['mountpoint'])
            if n.get('fstype'):
                fstypes.add(n['fstype'])
            for ch in n.get('children', []):
                walk(ch)
        walk(d)
        use_smart = HAS['smartctl'] and IS_ROOT and not d['name'].startswith('mmcblk')
        out.append({'name': d['name'], 'size': int(d['size']), 'model': (d.get('model') or '').strip(),
                    'serial': d.get('serial'), 'tran': d.get('tran'), 'rota': d.get('rota') in (True, '1', 1),
                    'mounts': mounts, 'fstypes': sorted(fstypes),
                    'smart': smart('/dev/' + d['name']) if use_smart else {}})
    return out


FS_TYPES = ('ext4', 'ext3', 'xfs', 'btrfs', 'vfat', 'f2fs', 'ntfs', 'ntfs3', 'exfat')


def filesystems():
    out, seen = [], set()
    for line in read('/proc/mounts').splitlines():
        dev, mnt, typ = line.split()[:3]
        mnt = mnt.replace('\\040', ' ')
        # only top-level ZFS datasets: children are listed under zfs.datasets
        if '@' in dev or '/.zfs/' in mnt:
            continue      # mounted snapshots
        # the root filesystem always counts, even when it is a ZFS subvolume (LXC containers)
        if mnt == '/' or typ in FS_TYPES or (typ == 'zfs' and dev.count('/') <= 1):
            if dev in seen and typ != 'zfs':
                continue      # bind mounts of the same device
            seen.add(dev)
            try:
                st = os.statvfs(mnt)
            except OSError:
                continue
            tot = st.f_blocks * st.f_frsize
            if tot:
                out.append({'mount': mnt, 'dev': dev, 'type': typ, 'total': tot,
                            'used': tot - st.f_bfree * st.f_frsize, 'avail': st.f_bavail * st.f_frsize})
    return out


def zfs():
    pools = []
    for line in sh(['zpool', 'list', '-Hp', '-o', 'name,size,alloc,free,frag,health']).splitlines():
        n, s, a, f, fr, h = line.split('\t')
        scan = re.search(r'scan: (.*)', sh(['zpool', 'status', n]))
        pools.append({'name': n, 'size': int(s), 'alloc': int(a), 'free': int(f),
                      'frag': fr, 'health': h, 'scan': scan.group(1).strip() if scan else ''})
    datasets = []
    for line in sh(['zfs', 'list', '-Hp', '-o', 'name,used,avail,mountpoint,compressratio']).splitlines():
        n, u, a, m, cr = line.split('\t')
        datasets.append({'name': n, 'used': int(u), 'avail': int(a), 'mount': m, 'ratio': cr})
    return {'pools': pools, 'datasets': datasets}


def backup_dirs():
    """Directory storages that hold vzdump backups, read from the Proxmox storage config."""
    dirs, cur = [], {}
    for line in read('/etc/pve/storage.cfg').splitlines() + ['']:
        if not line.strip():
            if cur.get('type') == 'dir' and 'backup' in cur.get('content', '') and cur.get('path'):
                dirs.append((cur['name'], cur['path']))
            cur = {}
        elif not line.startswith((' ', '\t')) and ':' in line:
            t, name = line.split(':', 1)
            cur = {'type': t.strip(), 'name': name.strip()}
        else:
            k, _, v = line.strip().partition(' ')
            cur[k] = v.strip()
    return dirs


def backups():
    """Most recent vzdump archive per guest and storage."""
    res = {}
    for name, path in backup_dirs():
        last = {}
        for f in glob.glob(path + '/dump/vzdump-*-*.*'):
            m = re.match(r'vzdump-(lxc|qemu)-(\d+)-(\d{4}_\d\d_\d\d-\d\d_\d\d_\d\d)\.(tar|vma)', os.path.basename(f))
            if not m:
                continue
            ts = time.mktime(time.strptime(m.group(3), '%Y_%m_%d-%H_%M_%S'))
            if ts > last.get(m.group(2), {}).get('ts', 0):
                last[m.group(2)] = {'ts': ts, 'size': os.path.getsize(f)}
        if last:
            res[name] = {'guests': last}
    return res


def slow_loop():
    while True:
        if HAS['lsblk'] and not CONTAINER:
            put('disks', disks())
        put('fs', filesystems())
        if HAS['zpool']:
            put('zfs', zfs())
        if HAS['pvesh']:
            try:
                put('storage', json.loads(sh(['pvesh', 'get', '/nodes/%s/storage' % NODE, '--output-format', 'json'])))
            except ValueError:
                pass
            put('backups', backups())
        put('slow_ts', time.time())
        time.sleep(60)


def static_info():
    cpu = re.search(r'model name\s*:\s*(.*)', read('/proc/cpuinfo')) or \
        re.search(r'Model\s*:\s*(.*)', read('/proc/cpuinfo'))       # ARM boards
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read('/etc/os-release'), re.M))
    pve = sh(['pveversion']).strip().split(' ')[0].replace('pve-manager/', '').split('/')[0] if HAS['pvesh'] else None
    put('host', {'node': NODE, 'cpu_model': cpu.group(1).strip() if cpu else '', 'threads': os.cpu_count(),
                 'kernel': os.uname().release, 'arch': os.uname().machine,
                 'os': osr.get('PRETTY_NAME', ''), 'pve': pve, 'container': CONTAINER})
    put('agent', {'version': VERSION, 'protocol': PROTOCOL, 'root': IS_ROOT,
                  'features': sorted(k for k, v in HAS.items() if v)})


def main():
    once = '--once' in sys.argv or 'once' in os.environ.get('SSH_ORIGINAL_COMMAND', '')
    static_info()
    for fn in (fast_loop, guests_loop, slow_loop):
        threading.Thread(target=fn, daemon=True).start()
    time.sleep(1.5)
    if once:      # connection test: wait for the slow collectors too
        for _ in range(60):
            with lock:
                if 'slow_ts' in state:
                    break
            time.sleep(0.5)
    try:
        while True:
            with lock:
                line = json.dumps(state, separators=(',', ':'))
            sys.stdout.write(line + '\n')
            sys.stdout.flush()
            if once:
                break
            time.sleep(1)
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    os._exit(0)


if __name__ == '__main__':
    main()
