"""Proxmox VE: start, shut down, reboot and stop guests from the panel.

Needs an API token on each host that should allow it:

    [[hosts]]
    id = "pve1"
    address = "192.168.1.10"
    api_token = "env:FARO_PVE1_TOKEN"     # faro@pve!faro=xxxxxxxx-xxxx-...

Give the token only VM.PowerMgmt (see docs/proxmox.md): it can switch guests
on and off and nothing else.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import Action, BasePlugin

OPS = ('start', 'shutdown', 'reboot', 'stop')
TEXT = {
    'en': {'start': 'Starting {n}.', 'shutdown': 'Shutting down {n}.', 'reboot': 'Rebooting {n}.',
           'stop': 'Forcing {n} off.', 'bad': 'Invalid request.', 'missing': 'No such guest.',
           'denied': 'Proxmox refused it (missing permission?): HTTP {c}.', 'fail': 'Could not do it: {e}.',
           'label': 'Power a VM or container'},
    'es': {'start': 'Encendiendo {n}.', 'shutdown': 'Apagando {n}.', 'reboot': 'Reiniciando {n}.',
           'stop': 'Forzando el apagado de {n}.', 'bad': 'Petición no válida.', 'missing': 'No encuentro esa máquina.',
           'denied': 'Proxmox lo ha rechazado (¿falta permiso?): HTTP {c}.', 'fail': 'No he podido: {e}.',
           'label': 'Encender o apagar una VM o contenedor'},
}


class Plugin(BasePlugin):
    name = 'proxmox'

    def __init__(self, app, options):
        super().__init__(app, options)
        self.T = TEXT.get(app.lang, TEXT['en'])
        self.ctx = ssl.create_default_context()
        if not options.get('verify_tls', False):       # Proxmox ships a self-signed certificate
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        self.hosts = {h['id']: h for h in app.conf['hosts'] if h.get('api_token')}

    def _api(self, host, path, method='GET', data=None):
        req = urllib.request.Request(host['api_url'] + '/api2/json' + path, method=method,
                                     data=urllib.parse.urlencode(data).encode() if data is not None else None,
                                     headers={'Authorization': 'PVEAPIToken=' + host['api_token']})
        with urllib.request.urlopen(req, timeout=30, context=self.ctx) as r:
            return json.loads(r.read() or b'{}').get('data')

    def power(self, host=None, vmid=None, op=None, **_):
        T = self.T
        h = self.hosts.get(host)
        if not h or op not in OPS:
            return {'ok': False, 'text': T['bad']}
        d = self.app.hosts.data(host) or {}
        g = next((x for x in d.get('guests') or [] if str(x['vmid']) == str(vmid)), None)
        if not g:
            return {'ok': False, 'text': T['missing']}
        node = (d.get('host') or {}).get('node')
        try:
            self._api(h, f'/nodes/{node}/{g["kind"]}/{int(vmid)}/status/{op}', 'POST', {})
        except urllib.error.HTTPError as e:
            return {'ok': False, 'text': T['denied'].format(c=e.code)}
        except Exception as e:
            return {'ok': False, 'text': T['fail'].format(e=type(e).__name__)}
        return {'ok': True, 'text': T[op].format(n=g['name'])}

    def actions(self):
        if not self.hosts:
            return []
        return [Action('guest.power', self.T['label'], self.power, confirm=True,
                       params={'host': list(self.hosts), 'vmid': 'int', 'op': list(OPS)})]
