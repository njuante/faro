// UI strings. To add a language, copy the `en` block, translate it and add it to STRINGS.

const en = {
  loading: 'Connecting…',
  login_title: 'Sign in', password: 'Password', login: 'Sign in', wrong_password: 'Wrong password.',
  too_many: 'Too many attempts. Wait a few minutes.', logout: 'Sign out',
  tab_home: 'Home', tab_system: 'System', tab_services: 'Services', tab_disks: 'Disks', tab_settings: 'Settings',
  back: 'Home', live: 'live', offline_conn: 'reconnecting',
  // home
  all_good: 'All good · {up} of {total} services', checking: 'Checking services…',
  down_one: '{names} is down', down_many: '{names} are down', no_connection: 'No connection to faro',
  ring_services: 'Services', ring_cpu: 'CPU', ring_temp: 'Temp.', ring_disk: 'Disk',
  // summary
  sum_services: 'Services', sum_hosts: 'Hosts', sum_hottest: 'Hottest', sum_storage: 'Storage', sum_net: 'Network now',
  all_responding: 'all responding', n_down: '{n} not responding', online_of: '/ {n} online',
  guests_on: '{on} of {n} guests running', cpu_of: 'CPU of {name}', disks_ok: '{n} disks, all healthy',
  disks_bad: '{n} disks · {bad} with warnings', physical_nics: 'main NIC of every host',
  // system
  online: 'online', no_data: 'no data', cpu: 'CPU', cpu_temp: 'CPU temperature', memory: 'Memory', net_now: 'Network now',
  load: 'load', peak_15: '15 min peak {v} °C', of: 'of', up_for: 'up {d}', threads: 'threads',
  per_thread: 'Load per thread · {n}', sensors: 'Sensors', offline_msg: 'No data from {name} ({address}).',
  retrying: 'Retrying automatically.', range_live: '15 min', range_day: '24 h',
  ch_temp: 'Temperature', ch_cpu: 'CPU usage', ch_net: 'Network', ch_mem: 'Memory',
  s_cpu_med: 'CPU (5 s median)', s_disk_hot: 'Hottest disk', s_down: 'Down', s_up: 'Up', s_ram: 'RAM used',
  ago_24: '24 h ago', ago_12: '12 h ago', ago_15: '15 min ago', ago_7: '7 min ago', now: 'now',
  containers: 'Containers',
  // services
  status: 'Status', service: 'Service', address: 'Address', where: 'Where', response: 'Response',
  last_checks: 'Last {n} checks', uptime: 'Up', responds: 'up', not_responding: 'down', checking_s: 'checking',
  available: '{p} % available', stable_since: 'stable {ago}', down_since: 'down {ago}',
  checked: 'checked {ago} · every {n} s', other_guests: 'Other VMs and containers', stopped: 'stopped',
  cores: 'cores', no_check: 'not checked',
  reason: { refused: 'port closed', timeout: 'no answer', unreachable: 'unreachable', certificate: 'invalid certificate',
            dns: 'name does not resolve' },
  // disks
  disks: 'Disks', storage: 'Storage', backups: 'Backups', uncatalogued: 'Add a label in faro.toml → [[disks]].',
  not_mounted: 'Not mounted', health: 'Health', model: 'Model', usage: 'Usage', now_io: 'Now', years: 'years',
  wear: 'wear', smart_ok: 'SMART healthy', smart_fail: 'SMART failing', bad_sectors: '{n} bad sectors',
  standby: 'sleeping', no_smart: 'no SMART', root: 'root', none_yet: 'none yet', what: 'What',
  // time
  never: 'never', just_now: 'just now', min_ago: '{n} min ago', h_ago: '{n} h ago', d_ago: '{n} days ago',
  // sheet / settings
  settings: 'Settings', theme: 'Theme', auto: 'Auto', light: 'Light', dark: 'Dark', language: 'Language',
  effects: 'Glass effects', effects_note: 'Turn them off if it stutters on an old device',
  connection: 'Connection', version: 'Version', install_app: 'Install the app', test_notify: 'Send a test notification',
  notify_sent: 'Test sent.', notify_none: 'Sent to the bell only: no notifier configured.',
  open: 'Open', open_url: 'Open {name}', response_time: 'Response time', availability: 'Availability',
  guest: 'Guest', long_press: 'Long-press an app for details.',
  // alerts
  alerts: 'Alerts', no_alerts: 'No alerts yet. When something breaks, it shows up here.', all: 'All',
  problems: 'Problems', today: 'Today',
  // actions
  start: 'Start', shutdown: 'Shut down', reboot: 'Reboot', stop: 'Force off', confirm_again: 'Tap again to confirm',
  working: 'Working…',
};

const es = {
  loading: 'Conectando…',
  login_title: 'Entrar', password: 'Contraseña', login: 'Entrar', wrong_password: 'Contraseña incorrecta.',
  too_many: 'Demasiados intentos. Espera unos minutos.', logout: 'Cerrar sesión',
  tab_home: 'Inicio', tab_system: 'Sistema', tab_services: 'Servicios', tab_disks: 'Discos', tab_settings: 'Ajustes',
  back: 'Inicio', live: 'en directo', offline_conn: 'reconectando',
  all_good: 'Todo en marcha · {up} de {total} servicios', checking: 'Comprobando los servicios…',
  down_one: 'No responde {names}', down_many: 'No responden {names}', no_connection: 'Sin conexión con faro',
  ring_services: 'Servicios', ring_cpu: 'CPU', ring_temp: 'Temp.', ring_disk: 'Disco',
  sum_services: 'Servicios', sum_hosts: 'Máquinas', sum_hottest: 'Más caliente', sum_storage: 'Almacenamiento',
  sum_net: 'Red ahora', all_responding: 'todos responden', n_down: '{n} sin responder', online_of: '/ {n} en línea',
  guests_on: '{on} de {n} invitados encendidos', cpu_of: 'CPU de {name}', disks_ok: '{n} discos, todos bien',
  disks_bad: '{n} discos · {bad} con avisos', physical_nics: 'tarjeta principal de cada máquina',
  online: 'en línea', no_data: 'sin datos', cpu: 'CPU', cpu_temp: 'Temperatura CPU', memory: 'Memoria',
  net_now: 'Red ahora', load: 'carga', peak_15: 'pico 15 min {v} °C', of: 'de', up_for: 'encendido {d}',
  threads: 'hilos', per_thread: 'Carga por hilo · {n}', sensors: 'Sensores',
  offline_msg: 'No llegan datos de {name} ({address}).', retrying: 'Se reintenta solo.',
  range_live: '15 min', range_day: '24 h',
  ch_temp: 'Temperatura', ch_cpu: 'Uso de CPU', ch_net: 'Red', ch_mem: 'Memoria RAM',
  s_cpu_med: 'CPU (mediana 5 s)', s_disk_hot: 'Disco más caliente', s_down: 'Bajada', s_up: 'Subida', s_ram: 'RAM usada',
  ago_24: 'hace 24 h', ago_12: 'hace 12 h', ago_15: 'hace 15 min', ago_7: 'hace 7 min', now: 'ahora',
  containers: 'Contenedores',
  status: 'Estado', service: 'Servicio', address: 'Dirección', where: 'Dónde', response: 'Respuesta',
  last_checks: 'Últimas {n} comprobaciones', uptime: 'Encendido', responds: 'responde', not_responding: 'no responde',
  checking_s: 'comprobando', available: '{p} % disponible', stable_since: 'estable {ago}', down_since: 'caído {ago}',
  checked: 'comprobado {ago} · cada {n} s', other_guests: 'Otras VMs y contenedores', stopped: 'apagada',
  cores: 'núcleos', no_check: 'sin comprobar',
  reason: { refused: 'puerto cerrado', timeout: 'no contesta', unreachable: 'sin conexión',
            certificate: 'certificado no válido', dns: 'el nombre no resuelve' },
  disks: 'Discos', storage: 'Almacenamiento', backups: 'Copias', uncatalogued: 'Ponle nombre en faro.toml → [[disks]].',
  not_mounted: 'Sin montar', health: 'Estado', model: 'Modelo', usage: 'Uso', now_io: 'Ahora', years: 'años',
  wear: 'desgaste', smart_ok: 'SMART correcto', smart_fail: 'SMART con fallos', bad_sectors: '{n} sectores malos',
  standby: 'en reposo', no_smart: 'sin SMART', root: 'raíz', none_yet: 'aún ninguna', what: 'Qué',
  never: 'nunca', just_now: 'hace un momento', min_ago: 'hace {n} min', h_ago: 'hace {n} h', d_ago: 'hace {n} días',
  settings: 'Ajustes', theme: 'Tema', auto: 'Automático', light: 'Claro', dark: 'Oscuro', language: 'Idioma',
  effects: 'Efectos de cristal', effects_note: 'Quítalos si va a tirones en un aparato antiguo',
  connection: 'Conexión', version: 'Versión', install_app: 'Instalar la app', test_notify: 'Enviar un aviso de prueba',
  notify_sent: 'Aviso enviado.', notify_none: 'Solo en la campana: no hay ningún canal de avisos configurado.',
  open: 'Abrir', open_url: 'Abrir {name}', response_time: 'Tiempo de respuesta', availability: 'Disponibilidad',
  guest: 'Invitado', long_press: 'Mantén pulsada una app para ver sus detalles.',
  alerts: 'Avisos', no_alerts: 'Aún no hay avisos. Cuando algo falle, aparecerá aquí.', all: 'Todo',
  problems: 'Problemas', today: 'Hoy',
  start: 'Encender', shutdown: 'Apagar', reboot: 'Reiniciar', stop: 'Forzar apagado', confirm_again: 'Pulsa otra vez para confirmar',
  working: 'Un momento…',
};

export const STRINGS = { en, es };
export const LANGS = { en: 'English', es: 'Español' };

let lang = 'en';

export function setLanguage(configured) {
  let wanted = null;
  try { wanted = localStorage.getItem('faro-lang'); } catch (e) { /* private mode */ }
  if (!wanted || !STRINGS[wanted]) wanted = configured && configured !== 'auto' ? configured : null;
  if (!wanted || !STRINGS[wanted]) wanted = (navigator.language || 'en').slice(0, 2);
  lang = STRINGS[wanted] ? wanted : 'en';
  document.documentElement.lang = lang;
  return lang;
}

export const getLanguage = () => lang;
export const locale = () => (lang === 'es' ? 'es-ES' : 'en-GB');

// t('down_one', { names: 'Plex' })
export function t(key, vars) {
  let s = STRINGS[lang][key] ?? en[key] ?? key;
  if (vars && typeof s === 'string') s = s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
  return s;
}
