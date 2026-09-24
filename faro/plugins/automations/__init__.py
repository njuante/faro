"""Automations: things faro does by itself. Each rule is enabled by giving it a table,
and can then be switched off and on from its card on the home screen.

    [plugins.automations.restart_down]      # restart the container of a service that stopped answering
    after_minutes = 2
    exclude = ["proxy"]                     # service ids never to restart

    [plugins.automations.idle_shutdown]     # shut down VMs nobody is using
    guests = ["pve1:107"]
    idle_minutes = 25
    below_cores = 0.08                      # "idle": using less than 8 % of one core

    [plugins.automations.report]            # a daily summary as a notification
    at = "22:00"

restart_down and idle_shutdown act through the proxmox plugin, so they need it
enabled and an api_token on the host. Every run is logged and shown on the card.
"""
import json
import os
import threading
import time
from collections import deque

from .. import Action, BasePlugin

TEXT = {
    'en': {
        'restart_down': ('Restart what stops answering', 'If a service in a container stops answering for {after} min, '
                         'its container is restarted once and you get a notification.'),
        'idle_shutdown': ('Shut down idle VMs', '{guests}: shut down after {idle} min without use, with a warning 5 min before.'),
        'report': ('Daily report', 'At {at}, a short summary of the day as a notification.'),
        'restarting': '{name} was not answering: restarting its container',
        'restarting_body': 'Down for {mins} min. faro restarts it once per incident.',
        'no_proxmox': '{name} is down but faro cannot restart it: enable the proxmox plugin and set an api_token.',
        'warn': '{name} shuts down in 5 minutes', 'warn_body': 'Nobody has used it for {mins} minutes.',
        'off': '{name} shut down', 'off_body': 'It had been idle for {mins} minutes.',
        'report_title': 'Daily report', 'report_now': 'Send me the report now', 'report_sent': 'Report on its way.',
        'report_prompt': 'Write the daily report: in 3 or 4 short sentences, how the homelab did today (problems, '
                         'backups, anything worth knowing). No greetings.',
        'plain': '{up} of {total} services answering · {hosts} of {nhosts} hosts online · {alerts} alerts today',
    },
    'es': {
        'restart_down': ('Reiniciar lo que deja de responder', 'Si un servicio de un contenedor lleva {after} min sin '
                         'responder, se reinicia su contenedor una vez y te avisa.'),
        'idle_shutdown': ('Apagar VMs sin uso', '{guests}: se apagan tras {idle} min sin usarse, avisando 5 min antes.'),
        'report': ('Parte diario', 'A las {at}, un resumen corto del día como aviso.'),
        'restarting': '{name} no respondía: reinicio su contenedor',
        'restarting_body': 'Caído {mins} min. faro lo reinicia una vez por incidente.',
        'no_proxmox': '{name} está caído pero faro no puede reiniciarlo: activa el plugin proxmox y pon un api_token.',
        'warn': '{name} se apaga en 5 minutos', 'warn_body': 'Lleva {mins} minutos sin usarse.',
        'off': '{name} apagada', 'off_body': 'Llevaba {mins} minutos sin usarse.',
        'report_title': 'Parte diario', 'report_now': 'Mandarme el parte ahora', 'report_sent': 'El parte va de camino.',
        'report_prompt': 'Escribe el parte del día: en 3 o 4 frases cortas, cómo ha ido hoy el homelab (problemas, '
                         'copias, lo que convenga saber). Sin saludos.',
        'plain': '{up} de {total} servicios responden · {hosts} de {nhosts} máquinas en línea · {alerts} avisos hoy',
    },
}
RULES = ('restart_down', 'idle_shutdown', 'report')
TICK = 20


class Plugin(BasePlugin):
    name = 'automations'
    web = 'automations.js'

    def __init__(self, app, options):
        super().__init__(app, options)
        self.T = TEXT.get(app.lang, TEXT['en'])
        self.rules = {k: dict(options[k]) for k in RULES if isinstance(options.get(k), dict)}
        r = self.rules
        if 'restart_down' in r:
            r['restart_down'].setdefault('after_minutes', 2)
            r['restart_down'].setdefault('exclude', [])
        if 'idle_shutdown' in r:
            r['idle_shutdown'].setdefault('guests', [])
            r['idle_shutdown'].setdefault('idle_minutes', 25)
            r['idle_shutdown'].setdefault('below_cores', 0.08)
        if 'report' in r:
            r['report'].setdefault('at', '22:00')
        data = app.conf['server']['data_dir']
        self.state_path = os.path.join(data, 'automations.json')
        self.lock = threading.Lock()
        saved = self._load()
        self.enabled = {k: saved.get('enabled', {}).get(k, True) for k in self.rules}
        self.log = deque(saved.get('log', []), maxlen=50)
        self.report_day = saved.get('report_day') or (time.strftime('%Y-%m-%d') if time.strftime('%H:%M') >= r.get(
            'report', {}).get('at', '99:99') else '')       # first start after the hour: today's counts as sent
        self.down_since, self.restarted = {}, set()
        self.idle_since, self.warned = {}, set()

    # ------------------------------------------------------------------ persistence

    def _load(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        with self.lock:
            snap = {'enabled': self.enabled, 'log': list(self.log), 'report_day': self.report_day}
        tmp = self.state_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    def note(self, rule, text, ok=True):
        with self.lock:
            self.log.append({'ts': time.time(), 'rule': rule, 'text': text, 'ok': ok})
        self._save()
        print(f'automations: {rule}: {text}', flush=True)

    # ------------------------------------------------------------------ loop

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name='automations').start()

    def _loop(self):
        time.sleep(60)          # let data and checks arrive first
        while True:
            for rule, fn in (('restart_down', self.check_down), ('idle_shutdown', self.check_idle),
                             ('report', self.check_report)):
                if rule in self.rules and self.enabled.get(rule):
                    try:
                        fn()
                    except Exception as e:      # one broken rule must not stop the others
                        self.note(rule, f'{type(e).__name__}: {str(e)[:120]}', ok=False)
            time.sleep(TICK)

    def power(self, host, vmid, op):
        px = self.app.plugin('proxmox')
        if not px or host not in px.hosts:
            return None
        return px.power(host=host, vmid=vmid, op=op)

    def check_down(self, now=None):
        now = now or time.time()
        cfg = self.rules['restart_down']
        for s in self.app.conf['services']:
            if s.get('guest') is None or s['id'] in cfg['exclude']:
                continue
            st = self.app.checks.get(s['id']) or {}
            if st.get('up') is not False:
                self.down_since.pop(s['id'], None)
                self.restarted.discard(s['id'])        # recovered: a new incident may restart it again
                continue
            since = self.down_since.setdefault(s['id'], now)
            if s['id'] in self.restarted or now - since < cfg['after_minutes'] * 60:
                continue
            self.restarted.add(s['id'])
            mins = round((now - since) / 60)
            res = self.power(s['host'], s['guest'], 'reboot')
            if res is None:
                self.note('restart_down', self.T['no_proxmox'].format(name=s['name']), ok=False)
                continue
            title = self.T['restarting'].format(name=s['name'])
            self.app.alerts.emit('info' if res['ok'] else 'bad', title, self.T['restarting_body'].format(mins=mins)
                                 if res['ok'] else res['text'], 4)
            self.note('restart_down', f'{title} · {res["text"]}', res['ok'])

    def check_idle(self, now=None):
        now = now or time.time()
        cfg = self.rules['idle_shutdown']
        limit = cfg['idle_minutes'] * 60
        for key in cfg['guests']:
            host, _, vmid = key.partition(':')
            d = self.app.hosts.data(host) or {}
            g = next((x for x in d.get('guests') or [] if str(x['vmid']) == vmid), None)
            used = (d.get('gcpu') or {}).get(vmid, (d.get('gcpu') or {}).get(int(vmid) if vmid.isdigit() else vmid, 0))
            if not g or g['status'] != 'running' or used >= cfg['below_cores']:
                self.idle_since.pop(key, None)
                self.warned.discard(key)
                continue
            idle = now - self.idle_since.setdefault(key, now)
            name = g['name']
            if idle >= limit:
                res = self.power(host, vmid, 'shutdown')
                self.idle_since.pop(key, None)
                self.warned.discard(key)
                if res is None:
                    self.note('idle_shutdown', self.T['no_proxmox'].format(name=name), ok=False)
                    continue
                self.app.alerts.emit('info', self.T['off'].format(name=name),
                                     self.T['off_body'].format(mins=round(idle / 60)), 3)
                self.note('idle_shutdown', f'{self.T["off"].format(name=name)} · {res["text"]}', res['ok'])
            elif idle >= limit - 300 and key not in self.warned:
                self.warned.add(key)
                self.app.alerts.emit('info', self.T['warn'].format(name=name),
                                     self.T['warn_body'].format(mins=round(idle / 60)), 3)

    def check_report(self, now=None):
        now = now or time.time()
        today = time.strftime('%Y-%m-%d', time.localtime(now))
        if time.strftime('%H:%M', time.localtime(now)) < self.rules['report']['at'] or self.report_day == today:
            return
        self.report_day = today
        self._save()
        self.send_report()

    def send_report(self):
        text = None
        ai = self.app.plugin('ai')
        if ai and ai.url:
            try:
                slow, live = ai.state_text()
                msgs = [{'role': 'system', 'content': ai.system_prompt()},
                        {'role': 'user', 'content': f'{ai.T["state"]}:\n{slow}\n{live}\n\n{ai.T["question"]}: '
                                                    f'{self.T["report_prompt"]}'}]
                with ai.chat(msgs, stream=False, options={'num_predict': 220}) as r:
                    text = (json.loads(r.read())['message']['content'] or '').strip()
            except Exception:
                text = None                              # no model: fall back to plain figures
        if not text:
            text = self.plain_summary()
        self.app.alerts.emit('info', self.T['report_title'], text[:900], 3)
        self.note('report', text[:140])

    def plain_summary(self):
        app = self.app
        checked = [app.checks.get(s['id']) for s in app.conf['services']]
        checked = [c for c in checked if c]
        start = time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d'))
        return self.T['plain'].format(
            up=sum(1 for c in checked if c['up']), total=len(checked),
            hosts=sum(1 for h in app.conf['hosts'] if (app.hosts.seen(h['id']) or 0) > time.time() - 90),
            nhosts=len(app.conf['hosts']), alerts=sum(1 for a in app.alerts.recent(300) if a['ts'] >= start))

    # ------------------------------------------------------------------ api

    def describe(self):
        out = []
        for rule, cfg in self.rules.items():
            name, text = self.T[rule]
            if rule == 'idle_shutdown':
                guests = ', '.join(self.guest_name(k) for k in cfg['guests']) or '—'
                text = text.format(guests=guests, idle=cfg['idle_minutes'])
            else:
                text = text.format(after=cfg.get('after_minutes'), at=cfg.get('at'))
            out.append({'id': rule, 'name': name, 'text': text, 'on': self.enabled[rule]})
        return out

    def guest_name(self, key):
        host, _, vmid = key.partition(':')
        g = next((x for x in (self.app.hosts.data(host) or {}).get('guests') or [] if str(x['vmid']) == vmid), None)
        return g['name'] if g else key

    def routes(self):
        def get(req):
            with self.lock:
                log = list(self.log)[::-1][:15]
            return 200, {'rules': self.describe(), 'log': log}

        def toggle(req):
            rule = req.body.get('id')
            if rule not in self.rules:
                return 400, {'error': 'unknown rule'}
            self.enabled[rule] = bool(req.body.get('on'))
            self._save()
            return 200, {'rules': self.describe()}
        return {('GET', '/api/p/automations'): get, ('POST', '/api/p/automations/toggle'): toggle}

    def actions(self):
        if 'report' not in self.rules:
            return []

        def now(**_):
            threading.Thread(target=self.send_report, daemon=True).start()
            return {'ok': True, 'text': self.T['report_sent']}
        return [Action('report.now', self.T['report_now'], now)]
