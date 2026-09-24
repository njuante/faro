"""Command line: faro serve | demo | init | add-host | set-password | hash-password | check | test-notify"""
import argparse
import getpass
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time

from . import __version__
from .auth import hash_password
from .config import ConfigError, load, normalise, slug
from .hosts import AGENT, ssh_base

REPO = 'njuante/faro'      # GitHub repository, used for the raw install URLs
EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'faro.example.toml')


def die(msg, code=1):
    print(f'error: {msg}', file=sys.stderr)
    sys.exit(code)


def config_path(args):
    return args.config or os.environ.get('FARO_CONFIG') or '/etc/faro/faro.toml'


def load_or_die(args):
    try:
        return load(config_path(args))
    except ConfigError as e:
        die(str(e))


# ------------------------------------------------------------------ serve

def watch_config(path, mtime, on_change):
    """Restarts the process when the config changes, if the new one is valid."""
    while True:
        time.sleep(3)
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if m == mtime:
            continue
        mtime = m
        try:
            load(path)
        except ConfigError as e:
            print(f'config changed but is not valid, keeping the old one: {e}', flush=True)
            continue
        print('config changed: restarting', flush=True)
        on_change()


def cmd_serve(args):
    from .app import Faro
    from .web import serve
    conf = load_or_die(args)
    app = Faro(conf)
    app.start()

    def restart():
        try:
            app.hosts.save()
        except OSError:
            pass
        os.execv(sys.executable, [sys.executable, '-m', 'faro', *sys.argv[1:]])  # noqa: S606 (re-exec itself)
    threading.Thread(target=watch_config, args=(conf['_path'], os.path.getmtime(conf['_path']), restart),
                     daemon=True).start()
    serve(app)


def cmd_demo(args):
    from . import demo
    from .app import Faro
    from .web import serve
    raw = json.loads(json.dumps(demo.CONFIG))
    raw['server']['data_dir'] = tempfile.mkdtemp(prefix='faro-demo-')
    raw['server']['port'] = args.port
    raw['server']['bind'] = args.bind
    raw['language'] = args.language
    conf = normalise(raw)
    app = Faro(conf, demo=True)
    app.start()
    serve(app)


# ------------------------------------------------------------------ config helpers

def set_auth_hash(path, hashed):
    text = read(path)
    line = f'password_hash = "{hashed}"'
    if re.search(r'^\s*password_hash\s*=.*$', text, re.M):
        text = re.sub(r'^\s*password_hash\s*=.*$', line, text, count=1, flags=re.M)
    elif re.search(r'^\[auth\]\s*$', text, re.M):
        text = re.sub(r'^\[auth\]\s*$', '[auth]\n' + line, text, count=1, flags=re.M)
    else:
        text = text.rstrip('\n') + f'\n\n[auth]\n{line}\n'
    write_atomic(path, text)


def read(path):
    with open(path) as f:
        return f.read()


def write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    if os.path.exists(path):
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)


def ask_password():
    while True:
        p1 = getpass.getpass('New password: ')
        if len(p1) < 8:
            print('Use at least 8 characters.')
            continue
        if getpass.getpass('Repeat it: ') != p1:
            print('They do not match.')
            continue
        return p1


def toml_str(v):
    return json.dumps(v, ensure_ascii=False)     # a JSON string is a valid TOML basic string


def cmd_hash_password(args):
    print(hash_password(ask_password()))


def cmd_set_password(args):
    path = config_path(args)
    load_or_die(args)
    set_auth_hash(path, hash_password(ask_password()))
    print(f'Password saved in {path}.')


def cmd_init(args):
    path = config_path(args)
    if os.path.exists(path) and not args.force:
        die(f'{path} already exists (use --force to overwrite it)')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = read(EXAMPLE)
    name = socket.gethostname()
    # the machine running faro is always the first host, read locally without SSH
    text = re.sub(r'(?ms)^# >>> hosts.*?^# <<< hosts\n',
                  f'[[hosts]]\nid = {toml_str(slug(name))}\nname = {toml_str(name)}\n'
                  f'description = "This machine"\ntransport = "local"\n', text)
    # the example service points at the example host: start with none, the commented examples stay
    text = re.sub(r'(?ms)^# >>> services.*?^# <<< services\n', '', text)
    text = re.sub(r'^title = .*$', f'title = {toml_str(args.title or name)}', text, count=1, flags=re.M)
    write_atomic(path, text)
    os.chmod(path, 0o600)
    print(f'Created {path}.')
    if sys.stdin.isatty():
        set_auth_hash(path, hash_password(ask_password()))
        print('Password saved.')
    else:
        print('Set a password with: faro set-password')


# ------------------------------------------------------------------ hosts

INSTALL_SH = r'''set -e
command -v python3 >/dev/null 2>&1 || { echo "faro: python3 is required on this host" >&2; exit 3; }
if [ "$(id -u)" = 0 ]; then dir=/usr/local/lib/faro; else dir="$HOME/.local/lib/faro"; fi
mkdir -p "$dir"
cat > "$dir/faro-agent.py.new" <<'FARO_AGENT_EOF'
__AGENT__
FARO_AGENT_EOF
chmod 755 "$dir/faro-agent.py.new"
mv "$dir/faro-agent.py.new" "$dir/faro-agent.py"
umask 077
mkdir -p "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
key='__KEY__'
body=$(echo "$key" | cut -d' ' -f2)
grep -vF "$body" "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.faro" || true
echo "command=\"python3 $dir/faro-agent.py\",restrict $key" >> "$HOME/.ssh/authorized_keys.faro"
mv "$HOME/.ssh/authorized_keys.faro" "$HOME/.ssh/authorized_keys"
command -v smartctl >/dev/null 2>&1 || echo "faro: tip: install smartmontools to see disk health" >&2
echo "faro: agent installed in $dir"
'''


def insert_host(text, block):
    """Adds a [[hosts]] block after the last one (or at the end), so hosts stay together."""
    last = list(re.finditer(r'(?ms)^\[\[hosts\]\].*?(?=^\[|^# -{10}|\Z)', text))
    if last:
        pos = last[-1].end()
        return text[:pos].rstrip('\n') + '\n' + block + '\n' + text[pos:].lstrip('\n')
    return text.rstrip('\n') + '\n' + block


def ensure_key(conf):
    ssh_dir = os.path.join(conf['server']['data_dir'], 'ssh')
    key = os.path.join(ssh_dir, 'id_ed25519')
    if not os.path.exists(key):
        os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', f'faro@{socket.gethostname()}',
                        '-f', key], check=True)
    return read(key + '.pub').strip()


def install_script(pub):
    return INSTALL_SH.replace('__AGENT__', read(AGENT)).replace('__KEY__', pub)


def test_host(conf, host):
    cmd = ssh_base(conf, host) + ['faro-agent', 'once']
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None, 'timed out'
    try:
        return json.loads(r.stdout.splitlines()[0]), None
    except (ValueError, IndexError):
        return None, (r.stderr or r.stdout).strip()[-400:] or f'exit code {r.returncode}'


def describe(d):
    h, a = d.get('host', {}), d.get('agent', {})
    extra = ', '.join(a.get('features', [])) or 'basic metrics'
    return (f'{h.get("node")} · {h.get("os")} · {h.get("cpu_model")} · {h.get("threads")} threads\n'
            f'  detected: {extra}{"" if a.get("root") else " (not root: no SMART)"}')


def cmd_add_host(args):
    path = config_path(args)
    conf = load_or_die(args)
    m = re.fullmatch(r'(?:([^@]+)@)?([^:@]+)(?::(\d+))?', args.target)
    if not m:
        die('target must look like user@address or user@address:port')
    user, address, port = m.group(1) or 'root', m.group(2), int(m.group(3) or 22)
    if args.id or args.name:
        hid = slug(args.id or args.name)
    elif re.fullmatch(r'[\d.]+', address):
        hid = 'host-' + address.split('.')[-1]          # 192.168.1.20 -> host-20
    else:
        hid = slug(address.split('.')[0])               # nas.lan -> nas
    if any(h['id'] == hid for h in conf['hosts']):
        die(f'there is already a host with id "{hid}" (choose another with --id)')
    host = {'id': hid, 'name': args.name or hid, 'address': address, 'user': user, 'port': port,
            'transport': 'ssh', 'nic': ''}

    pub = ensure_key(conf)
    print(f'Installing the agent on {user}@{address} (you may be asked for its password once)…', flush=True)
    # faro's own key is offered first (in case it is already authorised), then the password
    ssh_dir = os.path.join(conf['server']['data_dir'], 'ssh')
    ssh = ['ssh', '-i', os.path.join(ssh_dir, 'id_ed25519'), '-o', 'StrictHostKeyChecking=accept-new',
           '-o', 'UserKnownHostsFile=' + os.path.join(ssh_dir, 'known_hosts'),
           '-p', str(port), f'{user}@{address}', 'sh -s']
    r = subprocess.run(ssh, input=install_script(pub), text=True)
    if r.returncode != 0:
        die('the installation failed (see above)')

    print('Testing the connection with the restricted key…', flush=True)
    d, err = test_host(conf, host)
    if not d:
        die(f'the agent did not answer: {err}')
    print('  ' + describe(d))

    block = (f'\n[[hosts]]\nid = {toml_str(hid)}\nname = {toml_str(host["name"])}\n'
             f'address = {toml_str(address)}\n' + (f'user = {toml_str(user)}\n' if user != 'root' else '') +
             (f'port = {port}\n' if port != 22 else ''))
    if args.description:
        block += f'description = {toml_str(args.description)}\n'
    write_atomic(path, insert_host(read(path), block))
    load_or_die(args)
    print(f'Added "{hid}" to {path}. A running faro picks it up by itself in a few seconds.')


def cmd_agent_command(args):
    conf = load_or_die(args)
    pub = ensure_key(conf)
    print('Run this on the host to add (as the user faro should connect as, usually root):\n')
    print(f'curl -fsSL https://raw.githubusercontent.com/{REPO}/main/deploy/install-agent.sh | '
          f'sh -s -- {shlex.quote(pub)}')
    print('\nThen add it to the config with transport "ssh" and its address.')


def cmd_check(args):
    conf = load_or_die(args)
    print(f'{conf["_path"]}: OK · {len(conf["hosts"])} hosts, {len(conf["services"])} services, '
          f'{len(conf["plugins"])} plugins')
    if conf['auth']['mode'] == 'password' and not conf['auth']['password_hash']:
        print('warning: no password set yet: run `faro set-password`')
    if args.hosts:
        for h in conf['hosts']:
            if h['transport'] == 'local':
                r = subprocess.run([sys.executable, AGENT, '--once'], capture_output=True, text=True, timeout=90)
                d, err = (json.loads(r.stdout), None) if r.returncode == 0 else (None, r.stderr[-300:])
            else:
                d, err = test_host(conf, h)
            print(f'- {h["id"]}: ' + (describe(d) if d else f'FAILED: {err}'))


def cmd_test_notify(args):
    from .alerts import Notifier
    conf = load_or_die(args)
    n = Notifier(conf)
    if not n.enabled:
        die('no notifier configured: add [notify.ntfy] or [notify.webhook]')
    a = {'ts': time.time(), 'level': 'info', 'title': 'faro', 'body': 'Test notification', 'priority': 3,
         'url': None, 'key': None}
    for name, fn in (('ntfy', n._ntfy), ('webhook', n._webhook)):
        if getattr(n, name):
            try:
                fn(a)
                print(f'{name}: sent')
            except Exception as e:
                print(f'{name}: FAILED: {e}')


def main(argv=None):
    p = argparse.ArgumentParser(prog='faro', description='A self-hosted dashboard for your homelab servers.')
    p.add_argument('-c', '--config', help='config file (default: $FARO_CONFIG or /etc/faro/faro.toml)')
    p.add_argument('--version', action='version', version=f'faro {__version__}')
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('serve', help='run the dashboard').set_defaults(fn=cmd_serve)

    d = sub.add_parser('demo', help='run with made-up servers, no config needed')
    d.add_argument('--port', type=int, default=8080)
    d.add_argument('--bind', default='127.0.0.1')
    d.add_argument('--language', default='auto', choices=('auto', 'en', 'es'))
    d.set_defaults(fn=cmd_demo)

    i = sub.add_parser('init', help='create a config file for this machine')
    i.add_argument('--title')
    i.add_argument('--force', action='store_true')
    i.set_defaults(fn=cmd_init)

    a = sub.add_parser('add-host', help='install the agent on a server over SSH and add it')
    a.add_argument('target', help='user@address[:port]')
    a.add_argument('--id')
    a.add_argument('--name')
    a.add_argument('--description')
    a.set_defaults(fn=cmd_add_host)

    sub.add_parser('agent-command', help='print a one-liner to install the agent by hand').set_defaults(
        fn=cmd_agent_command)
    sub.add_parser('set-password', help='set the login password in the config').set_defaults(fn=cmd_set_password)
    sub.add_parser('hash-password', help='print a password hash').set_defaults(fn=cmd_hash_password)
    c = sub.add_parser('check', help='validate the config (and with --hosts, reach every agent)')
    c.add_argument('--hosts', action='store_true')
    c.set_defaults(fn=cmd_check)
    sub.add_parser('test-notify', help='send a test notification').set_defaults(fn=cmd_test_notify)

    args = p.parse_args(argv)
    args.fn(args)
