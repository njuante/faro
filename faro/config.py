"""Loads and validates faro.toml.

Any string value can point to a secret instead of holding it:
  "env:NAME"         read from the environment
  "file:/some/path"  read from a file (trailing newline stripped)
"""
import os
import re
import tomllib

DEFAULT_PATH = '/etc/faro/faro.toml'


class ConfigError(Exception):
    pass


def resolve(value, where):
    if not isinstance(value, str):
        return value
    if value.startswith('env:'):
        name = value[4:]
        if name not in os.environ:
            raise ConfigError(f'{where}: environment variable {name} is not set')
        return os.environ[name]
    if value.startswith('file:'):
        try:
            with open(value[5:]) as f:
                return f.read().rstrip('\n')
        except OSError as e:
            raise ConfigError(f'{where}: cannot read {value[5:]}: {e.strerror}') from None
    return value


def resolve_all(node, where=''):
    if isinstance(node, dict):
        return {k: resolve_all(v, f'{where}.{k}' if where else k) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_all(v, f'{where}[{i}]') for i, v in enumerate(node)]
    return resolve(node, where)


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-') or 'item'


def _unique_ids(items, kind):
    seen = set()
    for it in items:
        it.setdefault('id', slug(it.get('name', kind)))
        if it['id'] in seen:
            raise ConfigError(f'two {kind}s share the id "{it["id"]}": give one of them an explicit id')
        seen.add(it['id'])


def _check_url(value, where):
    if not re.match(r'^https?://', value or ''):
        raise ConfigError(f'{where}: "{value}" is not an http(s) URL')


def normalise(raw):
    c = resolve_all(raw)
    c.setdefault('title', 'faro')
    c.setdefault('language', 'auto')

    srv = c.setdefault('server', {})
    srv.setdefault('bind', '0.0.0.0')  # noqa: S104 (a dashboard for the LAN)
    srv.setdefault('port', 8080)
    srv.setdefault('data_dir', '/var/lib/faro')
    srv.setdefault('public_url', '')
    srv['public_url'] = srv['public_url'].rstrip('/')

    auth = c.setdefault('auth', {})
    auth.setdefault('mode', 'password')
    auth.setdefault('password_hash', '')
    auth.setdefault('session_days', 30)
    if auth['mode'] not in ('password', 'none'):
        raise ConfigError('auth.mode must be "password" or "none"')

    chk = c.setdefault('checks', {})
    chk.setdefault('interval', 10)
    chk.setdefault('timeout', 4)
    chk.setdefault('verify_tls', False)
    chk.setdefault('ca_file', '')

    al = c.setdefault('alerts', {})
    al.setdefault('service_down_after', 30)
    al.setdefault('host_offline_after', 90)
    al.setdefault('disk_temp_hdd', 60)
    al.setdefault('disk_temp_ssd', 70)
    al.setdefault('disk_temp_nvme', 80)
    al.setdefault('disk_full_percent', 90)

    hosts = c.setdefault('hosts', [])
    _unique_ids(hosts, 'host')
    for i, h in enumerate(hosts):
        where = f'hosts[{i}] ({h["id"]})'
        h.setdefault('name', h['id'])
        h.setdefault('transport', 'ssh')
        h.setdefault('user', 'root')
        h.setdefault('port', 22)
        h.setdefault('description', '')
        h.setdefault('nic', '')
        if h['transport'] not in ('ssh', 'local'):
            raise ConfigError(f'{where}: transport must be "ssh" or "local"')
        if h['transport'] == 'ssh' and not h.get('address'):
            raise ConfigError(f'{where}: missing address')
        h.setdefault('address', '127.0.0.1')
        if h.get('api_token'):
            h.setdefault('api_url', f'https://{h["address"]}:8006')
            if '=' not in h['api_token'] or '!' not in h['api_token']:
                raise ConfigError(f'{where}: api_token must look like "user@realm!name=secret"')

    host_ids = {h['id'] for h in hosts}
    services = c.setdefault('services', [])
    _unique_ids(services, 'service')
    for i, s in enumerate(services):
        where = f'services[{i}] ({s["id"]})'
        s.setdefault('name', s['id'])
        s.setdefault('description', '')
        s.setdefault('url', '')
        s.setdefault('group', '')
        s.setdefault('icon', '')
        s.setdefault('color', '')
        if s['url']:
            _check_url(s['url'], where)
        check = s.setdefault('check', 'http' if s['url'] else 'none')
        if check not in ('http', 'tcp', 'dns', 'none'):
            raise ConfigError(f'{where}: check must be http, tcp, dns or none')
        if check == 'http':
            s.setdefault('target', s['url'])
            _check_url(s['target'], where)
        elif check in ('tcp', 'dns') and not s.get('target'):
            raise ConfigError(f'{where}: a {check} check needs a target ("host:port" or "host")')
        if s.get('host') and s['host'] not in host_ids:
            raise ConfigError(f'{where}: unknown host "{s["host"]}"')
        if s.get('guest') is not None and not s.get('host'):
            raise ConfigError(f'{where}: "guest" needs "host" too')

    for i, d in enumerate(c.setdefault('disks', [])):
        if not d.get('host') or not d.get('serial'):
            raise ConfigError(f'disks[{i}]: needs host and serial')
    c.setdefault('guests', {})         # "host:vmid" -> description
    c.setdefault('backup_max_age', {}).setdefault('default', 26)     # hours, per backup storage

    nt = c.setdefault('notify', {})
    if nt.get('ntfy'):
        nt['ntfy'].setdefault('topic', 'faro')
        _check_url(nt['ntfy'].get('url'), 'notify.ntfy.url')
    if nt.get('webhook'):
        nt['webhook'].setdefault('format', 'json')
        _check_url(nt['webhook'].get('url'), 'notify.webhook.url')
        if nt['webhook']['format'] not in ('json', 'discord', 'slack'):
            raise ConfigError('notify.webhook.format must be json, discord or slack')

    c.setdefault('plugins', {})
    return c


def load(path=None):
    path = path or os.environ.get('FARO_CONFIG') or DEFAULT_PATH
    try:
        with open(path, 'rb') as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f'{path} does not exist (copy faro.example.toml to get started)') from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f'{path}: {e}') from None
    conf = normalise(raw)
    conf['_path'] = os.path.abspath(path)
    return conf


def public_view(conf):
    """The part of the config the browser gets: no secrets, no addresses it does not need."""
    return {
        'title': conf['title'],
        'language': conf['language'],
        'hosts': [{k: h[k] for k in ('id', 'name', 'description', 'nic')} | {'address': h['address'],
                   'actions': bool(h.get('api_token'))} for h in conf['hosts']],
        'services': [{k: s.get(k) for k in ('id', 'name', 'description', 'url', 'group', 'icon', 'color',
                                             'host', 'guest', 'check')} for s in conf['services']],
        'disks': [{k: d.get(k) for k in ('host', 'serial', 'label', 'role')} for d in conf['disks']],
        'guests': conf['guests'],
        'backup_max_age': conf['backup_max_age'],
        'check_interval': conf['checks']['interval'],
    }
