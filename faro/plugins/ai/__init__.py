"""Assistant: ask about your homelab in plain language, answered by a local model (Ollama).

    [plugins.ai]
    url = "http://192.168.1.30:11434"
    model = "qwen3:4b-instruct"
    guide = '''
    The NAS keeps the backups; the mini PC runs Jellyfin with its iGPU.
    Movies are requested in Jellyseerr (https://requests.example.com).
    '''

How it answers, in two calls to the model that share the same prompt prefix
(so Ollama reuses its cache and the second call only reads the new part):

1. With the question and a text summary of the live state, the model picks
   one tool (or none) in a JSON reply constrained by a schema.
2. faro runs that tool and the model writes the answer, streamed to the
   browser token by token.

Tools come from this plugin (CPU by guest, guests, disks, backups, alerts)
and from any other plugin (see Tool in faro/plugins). Nothing here changes
anything: every tool only reads.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque

from .. import BasePlugin, Tool
from ...i18n import gib

TEXT = {
    'en': {
        'system': """You are the assistant of a homelab dashboard called faro. You talk to the owner.
Rules:
1. Only talk about the homelab. For anything else answer only: "I can only help with the homelab 🙂".
2. Answer in English in 1 to 3 sentences, clear and direct. Use **bold** for what matters.
   Answer only what was asked: no extra advice and no questions at the end.
3. Live data is in STATE. How things are set up is in GUIDE. Use them and never make anything up.
   If the answer is in neither, say "I don't know" and suggest where to look.
4. Never say something is down, off or broken unless STATE says so explicitly.
5. If there is LOOKED UP data, answer with it: it is from right now and wins over STATE.
   You cannot change anything: if asked to, say which app or button to use.
6. Never mention tools, STATE or GUIDE by name: just answer.""",
        'empty': 'Nothing found: the list is empty.',
        'guide': 'GUIDE', 'none': 'nothing written yet',
        'tools_h': 'TOOLS (faro runs them for you and gives you the result as LOOKED UP data):',
        'tool_none': '- none: STATE or GUIDE already answer, or it is a greeting.',
        'decide': 'Internal step, do not answer yet: which tool do you need to answer the last QUESTION? Reply only with the JSON.',
        'state': 'STATE', 'question': 'QUESTION', 'looked': 'LOOKED UP just now with',
        'now': 'Now it is {when}.', 'no_data': '{name}: NO DATA (off or unreachable).',
        'host': '{name} ({desc}): CPU {cpu:.0f} %, RAM {used} of {total}{temp}, up {days:.0f} days.',
        'temp': ', CPU at {t:.0f} °C', 'pool': '  ZFS pool {name}: {health}, {pct:.0f} % used.',
        'fs': '  {mount}: {pct:.0f} % used, {free} free.', 'smart_ok': '  SMART: every disk healthy.',
        'smart_bad': '  SMART: PROBLEMS on {disks}.', 'guests': '  Running: {on}.', 'guests_off': ' Off: {off}.',
        'containers': '  Docker: {on} running{off}.', 'containers_off': ', stopped: {off}',
        'backup': '  Backups on {store}: newest {ago} ({n} guests).',
        'services': 'Services: {up} of {total} answering.', 'down': ' DOWN: {list}.',
        'problems': 'Open problems: {list}.', 'last_alerts': 'Latest alerts: {list}.',
        'ago_min': '{n} min ago', 'ago_h': '{n} h ago', 'ago_d': '{n} days ago', 'nothing': 'nothing',
        'offline': 'The assistant is not configured.', 'busy': 'Busy with another question; try again in a moment.',
        'no_question': 'The question is missing.', 'cannot': 'I cannot think right now: {why}.',
        'unreachable': 'the model server does not answer', 'waking': 'Waking the assistant up…',
        'looking': 'Looking it up…',
        't_cpu': ('Which guests used the most CPU on each host over the last 15 minutes, with average, min and max. '
                  'E.g. "why is the CPU high?"', 'Checking CPU usage…'),
        't_guests': ('Every VM and container on every host: running or stopped, cores, RAM, what it is for. '
                     'E.g. "is the Windows VM on?"', 'Checking the machines…'),
        't_disks': ('Every disk in detail: model, size, temperature, power-on hours, wear, SMART. '
                    'E.g. "how old are my disks?"', 'Checking the disks…'),
        't_backups': ('Latest Proxmox backup of each guest on each backup storage. E.g. "when was the last backup of '
                      'nextcloud?"', 'Checking the backups…'),
        't_alerts': ('The latest alerts with date and time. E.g. "what broke last night?"', 'Reading the alerts…'),
        'no_samples': 'Not enough data yet: faro just started, try again in a minute.',
        'unassigned': 'the rest is the host itself (ZFS, backups, the agent)',
    },
    'es': {
        'system': """Eres el asistente de un panel de homelab llamado faro. Hablas con su dueño.
Reglas:
1. SOLO hablas del homelab. Si preguntan otra cosa, responde únicamente: "Solo puedo ayudarte con el homelab 🙂".
2. Responde en español de España, en 1 a 3 frases, claro y directo. **Negrita** para lo importante.
   Contesta solo a lo que te preguntan: sin consejos extra y sin preguntas al final.
3. Los datos del momento están en ESTADO. Cómo está montado todo está en GUÍA. Úsalos y no inventes nada.
   Si la respuesta no está en ninguno, di "No lo sé" y sugiere dónde mirarlo.
4. No afirmes que algo está caído, apagado o roto si ESTADO no lo dice expresamente.
5. Si hay DATOS CONSULTADOS, contesta con ellos: son de ahora mismo y mandan sobre el ESTADO.
   No puedes cambiar nada: si te lo piden, di qué app o botón usar.
6. No nombres nunca las herramientas, el ESTADO ni la GUÍA: contesta directamente.""",
        'empty': 'No hay nada: la lista está vacía.',
        'guide': 'GUÍA', 'none': 'nada escrito todavía',
        'tools_h': 'HERRAMIENTAS (faro las ejecuta por ti y te da el resultado como DATOS CONSULTADOS):',
        'tool_none': '- ninguna: si el ESTADO o la GUÍA ya responden, o es un saludo.',
        'decide': 'Paso interno, no contestes aún: ¿qué herramienta necesitas para responder la última PREGUNTA? '
                  'Responde solo el JSON.',
        'state': 'ESTADO', 'question': 'PREGUNTA', 'looked': 'DATOS CONSULTADOS ahora con',
        'now': 'Ahora es {when}.', 'no_data': '{name}: SIN DATOS (apagado o sin conexión).',
        'host': '{name} ({desc}): CPU {cpu:.0f} %, RAM {used} de {total}{temp}, encendido hace {days:.0f} días.',
        'temp': ', CPU a {t:.0f} °C', 'pool': '  Pool ZFS {name}: {health}, {pct:.0f} % ocupado.',
        'fs': '  {mount}: {pct:.0f} % ocupado, libres {free}.', 'smart_ok': '  SMART: todos los discos bien.',
        'smart_bad': '  SMART: PROBLEMAS en {disks}.', 'guests': '  Encendidas: {on}.', 'guests_off': ' Apagadas: {off}.',
        'containers': '  Docker: {on} en marcha{off}.', 'containers_off': ', paradas: {off}',
        'backup': '  Copias en {store}: la última {ago} ({n} máquinas).',
        'services': 'Servicios: {up} de {total} responden.', 'down': ' CAÍDOS: {list}.',
        'problems': 'Problemas abiertos: {list}.', 'last_alerts': 'Últimos avisos: {list}.',
        'ago_min': 'hace {n} min', 'ago_h': 'hace {n} h', 'ago_d': 'hace {n} días', 'nothing': 'nada',
        'offline': 'El asistente no está configurado.', 'busy': 'Estoy contestando otra pregunta; prueba en un momento.',
        'no_question': 'Falta la pregunta.', 'cannot': 'No puedo pensar ahora: {why}.',
        'unreachable': 'el servidor del modelo no contesta', 'waking': 'Despertando al asistente…',
        'looking': 'Consultando…',
        't_cpu': ('Qué máquinas gastaron más CPU en cada servidor en los últimos 15 minutos, con media, mínimo y máximo. '
                  'Ej.: "¿por qué va alta la CPU?"', 'Mirando el consumo…'),
        't_guests': ('Todas las VMs y contenedores de cada servidor: encendidas o apagadas, núcleos, RAM y para qué son. '
                     'Ej.: "¿está encendido el Windows?"', 'Mirando las máquinas…'),
        't_disks': ('Cada disco en detalle: modelo, tamaño, temperatura, horas de uso, desgaste, SMART. '
                    'Ej.: "¿qué edad tienen mis discos?"', 'Mirando los discos…'),
        't_backups': ('La última copia de Proxmox de cada máquina en cada almacenamiento de copias. '
                      'Ej.: "¿cuándo fue la última copia de nextcloud?"', 'Mirando las copias…'),
        't_alerts': ('Los últimos avisos con fecha y hora. Ej.: "¿qué falló anoche?"', 'Leyendo los avisos…'),
        'no_samples': 'Aún no hay datos: faro acaba de arrancar, prueba en un minuto.',
        'unassigned': 'el resto es el propio servidor (ZFS, copias, el agente)',
    },
}
DAYS = {'en': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        'es': ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']}


class Plugin(BasePlugin):
    name = 'ai'
    web = 'ai.js'

    def __init__(self, app, options):
        super().__init__(app, options)
        self.T = TEXT.get(app.lang, TEXT['en'])
        self.url = (options.get('url') or '').rstrip('/')
        self.model = options.get('model', 'qwen3:4b-instruct')
        self.label = options.get('label') or self.model
        self.guide = (options.get('guide') or '').strip()
        self.keep_alive = options.get('keep_alive', '30m')
        self.ctx_size = int(options.get('context', 6144))
        self.threads = options.get('threads')
        self.log_path = os.path.join(app.conf['server']['data_dir'], 'ai.jsonl') if options.get('log') else None
        self.demo = bool(options.get('demo'))
        self.turn = threading.Semaphore(1)           # a small model on a CPU: one question at a time
        self.samples = {}                            # host -> deque of (ts, cpu %, {vmid: cores})
        self.warm_at = 0

    # ------------------------------------------------------------------ setup

    def start(self):
        threading.Thread(target=self._sample_loop, daemon=True, name='ai-samples').start()

    def _sample_loop(self):
        """Every 5 s, CPU per guest: lets the assistant say what has been busy for the last 15 minutes."""
        while True:
            for h in self.app.conf['hosts']:
                d = self.app.hosts.data(h['id']) or {}
                if d.get('cpu'):
                    self.samples.setdefault(h['id'], deque(maxlen=180)).append(
                        (time.time(), d['cpu']['total'], dict(d.get('gcpu') or {})))
            time.sleep(5)

    def tools(self):
        T = self.T
        mk = lambda name, fn: Tool(name, T['t_' + name][0], fn, step=T['t_' + name][1])   # noqa: E731
        return [mk('cpu', self.t_cpu), mk('guests', self.t_guests), mk('disks', self.t_disks),
                mk('backups', self.t_backups), mk('alerts', self.t_alerts)]

    def routes(self):
        return {('GET', '/api/p/ai/status'): self.r_status,
                ('POST', '/api/p/ai/chat'): self.r_chat,
                ('POST', '/api/p/ai/sleep'): self.r_sleep}

    # ------------------------------------------------------------------ the prompt

    def ago(self, ts):
        s = time.time() - ts
        if s < 3600:
            return self.T['ago_min'].format(n=int(s // 60))
        if s < 172800:
            return self.T['ago_h'].format(n=int(s // 3600))
        return self.T['ago_d'].format(n=int(s // 86400))

    def system_prompt(self):
        """The fixed part goes first so Ollama can keep it cached between questions."""
        T = self.T
        tools = '\n'.join(f'- {t.name}(' + ', '.join(t.params) + f'): {t.description}' for t in self.app.tools.values())
        services = '\n'.join(f'- {s["name"]}' + (f' ({s["url"]})' if s['url'] else '') +
                             (f': {s["description"]}' if s['description'] else '') for s in self.app.conf['services'])
        return (f'{T["system"]}\n\n{T["guide"]}\n{self.guide or T["none"]}\n\n{T["tools_h"]}\n{tools}\n{T["tool_none"]}'
                + (f'\n\nServices:\n{services}' if services else ''))

    def state_text(self):
        """(slow, live): what barely changes first, so only the live tail is new to the model on each question."""
        T, app = self.T, self.app
        slow, live = [], []
        snaps = app.hosts.snapshot(False)
        for h in app.conf['hosts']:
            snap = snaps[h['id']]
            d = snap.get('data')
            if not snap['online'] or not d:
                slow.append(T['no_data'].format(name=h['name']))
                continue
            slow.append(f'{h["name"]}:')
            for p in (d.get('zfs') or {}).get('pools', []):
                slow.append(T['pool'].format(name=p['name'], health=p['health'], pct=100 * p['alloc'] / p['size']))
            for f in d.get('fs') or []:
                if f['type'] != 'zfs' and f['total']:
                    slow.append(T['fs'].format(mount=f['mount'], pct=100 * f['used'] / f['total'], free=gib(f['avail'])))
            smart = [x for x in d.get('disks') or [] if x.get('smart')]
            bad = [f'{x["name"]} ({x.get("model")})' for x in smart
                   if x['smart'].get('healthy') is False or x['smart'].get('realloc') or x['smart'].get('pending')]
            if smart:
                slow.append(T['smart_bad'].format(disks=', '.join(bad)) if bad else T['smart_ok'])
            gs = d.get('guests') or []
            if gs:
                on = ', '.join(f'{g["vmid"]} {g["name"]}' for g in gs if g['status'] == 'running') or T['nothing']
                off = ', '.join(f'{g["vmid"]} {g["name"]}' for g in gs if g['status'] != 'running')
                slow.append(T['guests'].format(on=on) + (T['guests_off'].format(off=off) if off else ''))
            cs = d.get('containers') or []
            if cs:
                off = ', '.join(c['name'] for c in cs if c['state'] != 'running')
                slow.append(T['containers'].format(on=sum(c['state'] == 'running' for c in cs),
                                                   off=T['containers_off'].format(off=off) if off else ''))
            for store, b in (d.get('backups') or {}).items():
                ts = [v['ts'] for v in (b.get('guests') or {}).values()]
                if ts:
                    slow.append(T['backup'].format(store=store, ago=self.ago(max(ts)), n=len(ts)))
            m = d.get('mem') or {}
            live.append(T['host'].format(
                name=h['name'], desc=h['description'] or d['host'].get('os', ''), cpu=d['cpu']['total'],
                used=gib(m.get('used', 0)), total=gib(m.get('total', 0)),
                temp=T['temp'].format(t=d['cpu_temp']) if d.get('cpu_temp') else '',
                days=d.get('uptime', 0) / 86400))
        down = [s['name'] for s in app.conf['services'] if (app.checks.get(s['id']) or {}).get('up') is False]
        checked = [s for s in app.conf['services'] if app.checks.get(s['id'])]
        live.append(T['services'].format(up=len(checked) - len(down), total=len(checked)) +
                    (T['down'].format(list=', '.join(down)) if down else ''))
        problems = app.alerts.active()
        if problems:
            live.append(T['problems'].format(list=', '.join(problems)))
        recent = app.alerts.recent(3)
        if recent:
            live.append(T['last_alerts'].format(list='; '.join(f'{a["title"]} ({self.ago(a["ts"])})' for a in recent)))
        now = time.localtime()
        days = DAYS.get(app.lang, DAYS['en'])
        live.insert(0, T['now'].format(when=f'{days[now.tm_wday]} {time.strftime("%Y-%m-%d %H:%M", now)}'))
        return '\n'.join(slow), '\n'.join(live)

    # ------------------------------------------------------------------ tools

    def names(self):
        return {(h['id'], str(g['vmid'])): g['name'] for h in self.app.conf['hosts']
                for g in (self.app.hosts.data(h['id']) or {}).get('guests') or []}

    def t_cpu(self):
        names, out = self.names(), {}
        for h in self.app.conf['hosts']:
            pts = list(self.samples.get(h['id']) or [])
            if len(pts) < 3:
                continue
            threads = ((self.app.hosts.data(h['id']) or {}).get('host') or {}).get('threads') or 1
            total = [p[1] for p in pts]
            avg = {}
            for _, _, g in pts:
                for k, v in g.items():
                    avg[k] = avg.get(k, 0) + v / len(pts)
            top = sorted(avg.items(), key=lambda kv: -kv[1])[:5]
            out[h['name']] = {'minutes': round((pts[-1][0] - pts[0][0]) / 60),
                              'cpu avg/min/max %': [round(sum(total) / len(total)), round(min(total)), round(max(total))],
                              'top guests (% of the host)': {f'{k} {names.get((h["id"], str(k)), "?")}':
                                                             round(100 * v / threads, 1) for k, v in top if v > 0.005},
                              'note': self.T['unassigned']}
        return out or {'result': self.T['no_samples']}

    def t_guests(self):
        out = []
        for h in self.app.conf['hosts']:
            for g in (self.app.hosts.data(h['id']) or {}).get('guests') or []:
                out.append({'host': h['name'], 'id': g['vmid'], 'name': g['name'], 'type': g['kind'],
                            'status': g['status'], 'cores': g.get('cpus'), 'ram': gib(g.get('maxmem') or 0),
                            'about': self.app.conf['guests'].get(f'{h["id"]}:{g["vmid"]}', '')})
        return out

    def t_disks(self):
        out = []
        for h in self.app.conf['hosts']:
            for x in (self.app.hosts.data(h['id']) or {}).get('disks') or []:
                cfg = next((c for c in self.app.conf['disks'] if c['host'] == h['id'] and c['serial'] == x.get('serial')), {})
                sm = x.get('smart') or {}
                out.append({'host': h['name'], 'disk': cfg.get('label') or x['name'], 'role': cfg.get('role', ''),
                            'model': x.get('model'), 'size': gib(x['size']), 'type': x.get('tran'),
                            'temp_c': sm.get('temp'), 'power_on_hours': sm.get('hours'), 'wear_pct': sm.get('wear'),
                            'smart_ok': sm.get('healthy'), 'bad_sectors': (sm.get('realloc') or 0) + (sm.get('pending') or 0)})
        return out

    def t_backups(self):
        names, out = self.names(), {}
        for h in self.app.conf['hosts']:
            for store, b in ((self.app.hosts.data(h['id']) or {}).get('backups') or {}).items():
                out[store] = {f'{vmid} {names.get((h["id"], vmid), "?")}': self.ago(v['ts'])
                              for vmid, v in sorted(b['guests'].items(), key=lambda kv: int(kv[0]))}
        return out

    def t_alerts(self):
        return [{'when': time.strftime('%Y-%m-%d %H:%M', time.localtime(a['ts'])), 'what': a['title'], 'detail': a['body']}
                for a in self.app.alerts.recent(15)]

    def run_tool(self, name, args):
        tool = self.app.tools.get(name)
        if not tool:
            return {'error': f'no tool called {name}'}
        try:
            result = tool.fn(**{k: str(v) for k, v in (args or {}).items() if k in tool.params})
            # an empty list makes small models say "I don't know": spell out that there is nothing
            return result if result not in ([], {}, None, '') else {'result': self.T['empty']}
        except Exception as e:
            return {'error': f'{type(e).__name__}: {str(e)[:150]}'}

    # ------------------------------------------------------------------ talking to Ollama

    def ollama(self, path, body=None, timeout=180):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={'Content-Type': 'application/json'})
        return urllib.request.urlopen(req, timeout=timeout)

    def chat(self, msgs, **extra):
        opts = {'temperature': 0.3, 'num_ctx': self.ctx_size, 'num_predict': 350}
        if self.threads:
            opts['num_thread'] = int(self.threads)
        opts.update(extra.pop('options', {}))
        return self.ollama('/api/chat', {'model': self.model, 'keep_alive': self.keep_alive, 'messages': msgs,
                                         'options': opts, **extra})

    def loaded(self):
        try:
            with self.ollama('/api/ps', timeout=4) as r:
                return any(m.get('name', '').startswith(self.model) or m.get('model') == self.model
                           for m in json.loads(r.read()).get('models', []))
        except Exception:
            return False

    def reachable(self):
        try:
            with self.ollama('/api/version', timeout=3):
                return True
        except Exception:
            return False

    def warm_up(self):
        """Loads the model and caches the fixed prompt in the background, so the first question is quick."""
        if time.time() - self.warm_at < 600 or not self.turn.acquire(blocking=False):
            return
        self.warm_at = time.time()

        def run():
            try:
                with self.chat([{'role': 'system', 'content': self.system_prompt()},
                                {'role': 'user', 'content': f'{self.T["state"]}:\n{self.state_text()[0]}'}],
                               stream=False, options={'num_predict': 1}) as r:
                    r.read()
            except Exception:
                self.warm_at = 0
            finally:
                self.turn.release()
        threading.Thread(target=run, daemon=True).start()

    def answer(self, messages, send):
        T = self.T
        hist = [{'role': 'assistant' if m.get('role') == 'assistant' else 'user', 'content': str(m.get('text', ''))[:800]}
                for m in messages[-7:] if m.get('text')]
        if not hist or hist[-1]['role'] != 'user':
            return send({'error': T['no_question']})
        if self.demo:
            return self.demo_answer(hist[-1]['content'], send)
        slow, live = self.state_text()
        question = hist[-1]['content']
        hist[-1]['content'] = f'{T["state"]}:\n{slow}\n{live}\n\n{T["question"]}: {question}'
        msgs = [{'role': 'system', 'content': self.system_prompt()}] + hist
        t0, used = time.time(), []

        # step 1: which tool? The schema limits the reply to real tool names.
        names = list(self.app.tools)
        schema = {'type': 'object', 'required': ['tool', 'argument'],
                  'properties': {'tool': {'type': 'string', 'enum': ['none'] + names}, 'argument': {'type': 'string'}}}
        try:
            with self.chat(msgs + [{'role': 'user', 'content': T['decide']}], stream=False, format=schema,
                           options={'temperature': 0, 'num_predict': 40}) as r:
                pick = json.loads(json.loads(r.read())['message']['content'])
        except Exception:
            pick = {'tool': 'none'}            # if deciding fails, answer without a tool
        tool = self.app.tools.get(pick.get('tool'))
        if tool:
            send({'step': tool.step or T['looking']})
            args = {k: pick.get('argument') or question for k in tool.params}
            result = self.run_tool(tool.name, args)
            used.append(tool.name)
            hist[-1]['content'] += (f'\n\n{T["looked"]} {tool.name}({", ".join(args.values())}):\n' +
                                    json.dumps(result, ensure_ascii=False, indent=0)[:3500])

        # step 2: the answer, streamed
        text, tps = [], None
        with self.chat(msgs, stream=True) as r:
            for line in r:
                d = json.loads(line)
                piece = (d.get('message') or {}).get('content')
                if piece:
                    text.append(piece)
                    send({'t': piece})
                if d.get('done'):
                    tps = round((d.get('eval_count') or 0) / (d.get('eval_duration') or 1) * 1e9, 1)
        self.warm_at = time.time()
        send({'done': True, 'tps': tps, 'tools': used})
        self.log(question, ''.join(text), time.time() - t0, used)

    def demo_answer(self, question, send):
        """No model in demo mode: a canned but truthful summary built from the live state."""
        slow, live = self.state_text()
        send({'step': self.T['looking']})
        time.sleep(0.8)
        lines = [ln for ln in live.split('\n')[1:] if ln]
        services = next((ln for ln in lines if ln.startswith(self.T['services'].split('{')[0])), '')
        text = f'**{services}**\n' + '\n'.join(ln for ln in lines if ln != services)
        for word in text.split(' '):
            send({'t': word + ' '})
            time.sleep(0.03)
        send({'done': True, 'tps': 18.5, 'tools': []})

    def log(self, question, answer, secs, tools):
        if not self.log_path:
            return
        try:
            fd = os.open(self.log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, 'a') as f:
                f.write(json.dumps({'ts': time.time(), 'question': question, 'answer': answer,
                                    'secs': round(secs, 1), 'tools': tools}, ensure_ascii=False) + '\n')
        except OSError:
            pass

    # ------------------------------------------------------------------ routes

    def r_status(self, req):
        if self.demo:
            return 200, {'ok': True, 'model': 'demo', 'loaded': True}
        ok = bool(self.url) and self.reachable()
        loaded = ok and self.loaded()
        if ok and req.query().get('warm') == '1':
            self.warm_up()
        return 200, {'ok': ok, 'model': self.label, 'loaded': loaded}

    def r_sleep(self, req):
        """Unloads the model to give its RAM back (it loads again on the next question)."""
        try:
            with self.ollama('/api/generate', {'model': self.model, 'keep_alive': 0, 'prompt': ''}, timeout=30) as r:
                r.read()
        except Exception as e:
            return 200, {'ok': False, 'text': type(e).__name__}
        self.warm_at = 0
        return 200, {'ok': True}

    def r_chat(self, req):
        send = req.sse()
        if not self.url and not self.demo:
            return send({'error': self.T['offline']})
        if not self.turn.acquire(timeout=90):
            return send({'error': self.T['busy']})
        try:
            self.answer(req.body.get('messages') or [], send)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            why = self.T['unreachable'] if isinstance(e, (urllib.error.URLError, TimeoutError, OSError)) else type(e).__name__
            try:
                send({'error': self.T['cannot'].format(why=why)})
            except OSError:
                pass
        finally:
            self.turn.release()
