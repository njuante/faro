"""Server-side strings (notifications). The web UI has its own table in web/js/i18n.js."""

STRINGS = {
    'en': {
        'svc_down': '{name} is down',
        'svc_down_body': '{what}{reason}',
        'svc_up': '{name} is back up',
        'svc_up_body': 'It was down for {dur}.',
        'host_off': '{name} stopped reporting',
        'host_off_body': 'No data from {name} ({address}) for over {secs} s: powered off, hung or offline.',
        'host_on': '{name} is back online',
        'host_on_body': 'No data for {dur}.',
        'smart_bad': 'Disk {name} is failing',
        'smart_bad_body': '{host} · {model}: {what}. Check that your backups are up to date.',
        'smart_failed': 'SMART reports a failure',
        'smart_sectors': '{n} bad sectors',
        'smart_ok': 'Disk {name}: SMART is healthy again',
        'smart_ok_body': 'The previous warning is gone.',
        'disk_hot': 'Disk {name} is too hot',
        'disk_hot_body': '{host}: {temp} °C for 5 minutes.',
        'disk_cool': 'Disk {name} has cooled down',
        'disk_cool_body': 'It was hot for {dur}.',
        'fs_full': '{mount} on {host} is almost full',
        'fs_full_body': '{pct} % used, {free} free.',
        'fs_ok': '{mount} on {host} has room again',
        'fs_ok_body': '{pct} % used.',
        'pool_bad': 'ZFS pool {name} is {health}',
        'pool_bad_body': '{host}: check `zpool status {name}`.',
        'pool_ok': 'ZFS pool {name} is ONLINE again',
        'pool_ok_body': '{host}',
        'reason': {'refused': 'port closed', 'timeout': 'no answer', 'unreachable': 'unreachable',
                   'certificate': 'invalid certificate', 'dns': 'name does not resolve'},
        'test': 'Test notification', 'test_body': 'If you can read this, notifications work.',
    },
    'es': {
        'svc_down': '{name} no responde',
        'svc_down_body': '{what}{reason}',
        'svc_up': '{name} vuelve a funcionar',
        'svc_up_body': 'Estuvo caído {dur}.',
        'host_off': '{name} no envía datos',
        'host_off_body': 'Sin noticias de {name} ({address}) desde hace más de {secs} s: apagado, colgado o sin red.',
        'host_on': '{name} vuelve a estar en línea',
        'host_on_body': 'Estuvo sin datos {dur}.',
        'smart_bad': 'Disco {name} con problemas',
        'smart_bad_body': '{host} · {model}: {what}. Revisa que las copias estén al día.',
        'smart_failed': 'SMART dice que el disco falla',
        'smart_sectors': '{n} sectores dañados',
        'smart_ok': 'Disco {name}: SMART vuelve a estar bien',
        'smart_ok_body': 'El aviso anterior ya no aparece.',
        'disk_hot': 'Disco {name} muy caliente',
        'disk_hot_body': '{host}: {temp} °C desde hace 5 minutos.',
        'disk_cool': 'Disco {name} ya se ha enfriado',
        'disk_cool_body': 'Estuvo caliente {dur}.',
        'fs_full': '{mount} en {host} está casi lleno',
        'fs_full_body': '{pct} % usado, quedan {free}.',
        'fs_ok': '{mount} en {host} vuelve a tener espacio',
        'fs_ok_body': '{pct} % usado.',
        'pool_bad': 'El pool ZFS {name} está {health}',
        'pool_bad_body': '{host}: revisa `zpool status {name}`.',
        'pool_ok': 'El pool ZFS {name} vuelve a estar ONLINE',
        'pool_ok_body': '{host}',
        'reason': {'refused': 'puerto cerrado', 'timeout': 'no contesta', 'unreachable': 'sin conexión',
                   'certificate': 'certificado no válido', 'dns': 'el nombre no resuelve'},
        'test': 'Aviso de prueba', 'test_body': 'Si lees esto, los avisos funcionan.',
    },
}


def strings(lang):
    return STRINGS.get(lang, STRINGS['en'])


def duration(sec, lang):
    m = round(sec / 60)
    if m < 90:
        return f'{m} min'
    h = f'{m / 60:.1f} h'
    return h.replace('.', ',') if lang == 'es' else h


def gib(n):
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        if n < 1024:
            return f'{n:.0f} {unit}' if unit in ('B', 'KiB') or n >= 100 else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} EiB'
