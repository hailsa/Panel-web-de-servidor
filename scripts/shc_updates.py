"""Host APT inventory and reviewed update jobs. Imported only by the root helper."""
import contextlib
import codecs
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import uuid

STATE = Path('/var/lib/shc-monitor-updates')
CACHE = Path('/var/cache/shc-monitor-updates')
HELPER = '/usr/local/libexec/shc-updates-helper'
TRACKER_URL = 'https://security-tracker.debian.org/tracker/data/json'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive',
       'APT_LISTCHANGES_FRONTEND': 'none', 'NEEDRESTART_MODE': 'l', 'HOME': '/root'}
APT_OPTIONS = ['--no-remove', '--no-install-recommends', '-o', 'DPkg::Lock::Timeout=0',
               '-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold',
               '-o', 'Dpkg::Use-Pty=0']


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as file:
        json.dump(value, file, ensure_ascii=False)
        temporary = file.name
    os.replace(temporary, path)


def command(args, timeout=40):
    result = subprocess.run(args, text=True, capture_output=True, env=ENV, timeout=timeout)
    if result.returncode:
        raise ValueError(redact(result.stderr[-1600:] or result.stdout[-1600:] or 'Falló la consulta del sistema.'))
    return result.stdout


def redact(text):
    text = re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[credenciales]@', text)
    return re.sub(r'(?i)([?&](?:token|password|key|secret)=)[^&\s]+', r'\1[oculto]', text)


def apt_cache():
    import apt
    import apt_pkg
    apt_pkg.config.set('APT::Install-Recommends', 'false')
    apt_pkg.config.set('APT::Install-Suggests', 'false')
    return apt.Cache(memonly=True)


def release():
    data = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            data[key] = value.strip('"')
    if data.get('ID') != 'debian':
        raise ValueError('Esta versión del gestor admite el anfitrión Debian con APT.')
    return data.get('VERSION_CODENAME', ''), data.get('PRETTY_NAME', 'Debian')


def is_security_origin(origin):
    return origin.trusted and origin.origin == 'Debian' and (origin.label == 'Debian-Security' or origin.archive.endswith('-security'))


def cves_for(row, tracker, codename, compare):
    found = []
    if not row['debian']:
        return found
    for name, issue in tracker.get(row['source_package'], {}).items():
        if not re.fullmatch(r'CVE-[0-9]{4}-[0-9]{4,}', name):
            continue
        info = issue.get('releases', {}).get(codename, {})
        fixed = info.get('fixed_version', '')
        if fixed == '0' or (fixed and compare(row['installed_source_version'], fixed) >= 0):
            continue
        if not fixed and info.get('status') not in {'open', 'undetermined'}:
            continue
        found.append({'id': name, 'description': issue.get('description', ''), 'urgency': info.get('urgency', 'not yet assigned'),
                      'fixed_version': fixed, 'fixed_by_candidate': bool(fixed and compare(row['candidate_source_version'], fixed) >= 0),
                      'status': info.get('status', 'unknown'), 'scope': issue.get('scope', 'unknown')})
    return sorted(found, key=lambda item: (not item['fixed_by_candidate'], urgency_rank(item['urgency']), item['id']))


def urgency_rank(value):
    return {'high': 0, 'medium': 1, 'low': 2, 'unimportant': 3}.get(value, 4)


def package_row(pkg):
    version = pkg.candidate
    installed = pkg.installed
    origins = [{'origin': o.origin, 'label': o.label, 'archive': o.archive, 'codename': getattr(o, 'codename', ''), 'site': o.site,
                'component': o.component, 'trusted': o.trusted} for o in version.origins]
    name = pkg.name.split(':')[0]
    return {'name': name, 'id': f'{name}:{version.architecture}', 'architecture': version.architecture,
            'installed': installed.version if installed else None, 'candidate': version.version,
            'source_package': version.source_name, 'installed_source_version': installed.source_version if installed else '',
            'candidate_source_version': version.source_version, 'summary': version.summary,
            'description': version.description[:12000], 'section': version.section, 'priority': version.priority,
            'download_bytes': version.size, 'origins': origins, 'trusted': any(o['trusted'] for o in origins),
            'debian': any(o['origin'] == 'Debian' and o['trusted'] for o in origins),
            'security_origin': any(is_security_origin(o) for o in version.origins),
            'held': pkg._pkg.selected_state == 2, 'security': False, 'urgency': 'not yet assigned', 'cves': []}


def reboot_status():
    import apt_pkg
    running = os.uname().release
    images = [p.name.removeprefix('vmlinuz-') for p in Path('/boot').glob('vmlinuz-*')]
    newer = [name for name in images if apt_pkg.version_compare(name, running) > 0]
    flag = Path('/run/reboot-required').exists()
    return {'required': flag or bool(newer), 'running_kernel': running, 'newer_kernels': newer,
            'reason': 'El sistema solicita reinicio.' if flag else 'Hay un kernel instalado más nuevo que el que está en uso.' if newer else ''}


def scan():
    import apt_pkg
    codename, os_name = release()
    cache = apt_cache()
    feed = read(CACHE / 'tracker.json', {})
    tracker = feed.get('sources', {})
    rows = []
    for pkg in cache:
        if not pkg.is_installed or not pkg.is_upgradable:
            continue
        row = package_row(pkg)
        row['cves'] = cves_for(row, tracker, codename, apt_pkg.version_compare)
        row['security'] = row['security_origin'] or any(cve['fixed_by_candidate'] for cve in row['cves'])
        fixed = [cve for cve in row['cves'] if cve['fixed_by_candidate']]
        row['urgency'] = min((cve['urgency'] for cve in fixed), key=urgency_rank, default='not yet assigned')
        rows.append(row)
    rows.sort(key=lambda row: (not row['security'], urgency_rank(row['urgency']), row['name']))
    result = {'available': True, 'scanned_at': time.time(), 'os': os_name, 'codename': codename, 'packages': rows,
              'security_count': sum(row['security'] for row in rows), 'total_count': len(rows),
              'high_count': sum(row['security'] and row['urgency'] == 'high' for row in rows),
              'held_count': sum(row['held'] for row in rows), 'reboot': reboot_status(),
              'tracker_checked_at': feed.get('checked_at'), 'tracker_error': feed.get('error'),
              'audit': command(['/usr/bin/dpkg', '--audit']).strip()[:4000]}
    write(CACHE / 'inventory.json', result)
    return result


def stream_tracker(stream, wanted, consume, maximum=256 * 1024 * 1024):
    """Read one source package at a time, without loading the entire CVE database."""
    def characters():
        decoder = codecs.getincrementaldecoder('utf-8')()
        total = 0
        while True:
            chunk = stream.read(65536)
            if not chunk:
                yield from decoder.decode(b'', final=True)
                return
            total += len(chunk)
            if total > maximum:
                raise ValueError('El feed de seguridad supera el límite de tamaño.')
            yield from decoder.decode(chunk)
    chars = iter(characters())
    def token():
        for char in chars:
            if not char.isspace():return char
        raise ValueError('El feed de seguridad está truncado.')
    def key(char):
        if char != '"':raise ValueError('Clave inválida en el feed.')
        key, escaped = ['"'], False
        for char in chars:
            key.append(char)
            if len(key) > 512:raise ValueError('Nombre de paquete fuente demasiado largo.')
            if char == '"' and not escaped:break
            if char == '\\' and not escaped:escaped=True
            else:escaped=False
        return json.loads(''.join(key))
    def object_value(keep):
        value, depth, quoted, escaped = ['{'], 1, False, False
        for char in chars:
            if keep:
                value.append(char)
                if len(value) > 4 * 1024 * 1024:raise ValueError('Registro CVE demasiado grande.')
            if quoted:
                if char == '"' and not escaped:quoted=False
                if char == '\\' and not escaped:escaped=True
                else:escaped=False
            elif char == '"':quoted=True
            elif char in '{[':depth+=1
            elif char in '}]':
                depth-=1
                if depth == 0:break
        if depth:raise ValueError('Registro de seguridad truncado.')
        return json.loads(''.join(value)) if keep else None
    if token() != '{':raise ValueError('Formato de seguridad inválido.')
    char = token()
    if char == '}':return
    while True:
        name = key(char)
        if token() != ':' or token() != '{':raise ValueError('Registro de seguridad inválido.')
        if name not in wanted:
            object_value(False)
        else:
            char = token()
            while char != '}':
                cve = key(char)
                if token() != ':' or token() != '{':raise ValueError('Registro CVE inválido.')
                consume(name, {cve: object_value(True)})
                char = token()
                if char == '}':break
                if char != ',':raise ValueError('Separador CVE inválido.')
                char = token()
        char = token()
        if char == '}':return
        if char != ',':raise ValueError('Separador de seguridad inválido.')
        char = token()


def refresh_tracker():
    import apt_pkg
    old = read(CACHE / 'tracker.json', {})
    cache = apt_cache()
    versions = {}
    for pkg in cache:
        if pkg.is_installed:
            installed = pkg.installed
            prior = versions.get(installed.source_name)
            if prior is None or apt_pkg.version_compare(installed.source_version, prior) < 0:
                versions[installed.source_name] = installed.source_version
    codename, _ = release()
    selected = {}
    def consume(name, issues):
        relevant = {}
        for cve, issue in issues.items():
            info = issue.get('releases', {}).get(codename, {})
            fixed = info.get('fixed_version', '')
            if fixed == '0' or fixed and apt_pkg.version_compare(versions[name], fixed) >= 0:
                continue
            if fixed or info.get('status') in {'open', 'undetermined'}:
                relevant[cve] = {'description': issue.get('description', ''), 'scope': issue.get('scope', 'unknown'), 'releases': {codename: info}}
        if relevant:selected.setdefault(name, {}).update(relevant)
    try:
        request = urllib.request.Request(TRACKER_URL, headers={'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(request, timeout=35) as response:
            stream = gzip.GzipFile(fileobj=response) if response.headers.get('Content-Encoding') == 'gzip' else response
            stream_tracker(stream, versions, consume)
        write(CACHE / 'tracker.json', {'checked_at': time.time(), 'sources': selected})
    except Exception as error:
        old['error'] = f'No se pudo actualizar Debian Security Tracker: {redact(str(error))[:180]}. La clasificación por repositorio sigue disponible.'
        write(CACHE / 'tracker.json', old)


def impact(names):
    services = set()
    mapping = {'apache2': 'Apache', 'docker': 'Docker', 'containerd': 'Docker/containerd', 'libvirt': 'KVM/libvirt',
               'qemu': 'KVM/QEMU', 'openssh': 'SSH', 'systemd': 'Servicios del sistema', 'zerotier': 'ZeroTier',
               'libc6': 'Procesos que usan libc', 'libssl': 'Servicios que usan OpenSSL'}
    for name in names:
        for prefix, service in mapping.items():
            if name.startswith(prefix):
                services.add(service)
    return sorted(services)


def parse_simulation(output):
    if re.search(r'^Remv\s', output, re.M):
        raise ValueError('La resolución requiere quitar paquetes. Esta acción no permite eliminaciones.')
    return re.findall(r'^Inst\s+(\S+)(?:\s+\[[^\]]*\])?\s+\((\S+)', output, re.M)


def validate_simulation(output, changes):
    expected = {item['id']: item['candidate'] for item in changes}
    actual = {}
    for name, version in parse_simulation(output):
        matches = [key for key in expected if key == name or (':' not in name and key.split(':')[0] == name)]
        if len(matches) != 1:
            raise ValueError('APT propone cambios distintos de los revisados. Volvé a simular.')
        actual[matches[0]] = version
    if actual != expected:
        raise ValueError('La simulación de APT no coincide con el plan. Volvé a consultar las actualizaciones.')


def specifications(changes):
    return [f"{item['id']}={item['candidate']}" for item in changes]


def build_plan(scope):
    import apt_pkg
    if scope not in {'all', 'security'}:
        raise ValueError('Elegí todas las actualizaciones o sólo seguridad.')
    checked = read(CACHE / 'last-check.json', {}).get('checked_at', 0)
    if time.time() - checked > 86400:
        raise ValueError('Primero usá Buscar actualizaciones; la consulta de índices debe tener menos de 24 horas.')
    inventory = scan()
    cache = apt_cache()
    if inventory['audit'] or cache.broken_count or cache.dpkg_journal_dirty:
        raise ValueError('DPKG tiene tareas pendientes o dependencias rotas. Revisá el estado antes de actualizar.')
    rows = {row['id']: row for row in inventory['packages']}
    selected = [row for row in rows.values() if not row['held'] and row['trusted'] and (scope == 'all' or row['security'])]
    selected_ids = {row['id'] for row in selected}
    with cache.actiongroup():
        for row in selected:
            cache[row['id']].mark_install(auto_fix=True, auto_inst=True, from_user=True)
    changes = []
    for pkg in cache.get_changes():
        if pkg.marked_delete:
            raise ValueError('Esta actualización necesita quitar paquetes. Se bloqueó el plan para evitar eliminaciones.')
        row = rows.get(f"{pkg.name.split(':')[0]}:{pkg.candidate.architecture}") or package_row(pkg)
        if row['held'] or not row['trusted']:
            raise ValueError(f"El plan afecta a {row['name']}, que está retenido o no tiene un origen confiable.")
        if row['debian'] and not any(origin['origin'] == 'Debian' and origin['trusted'] and origin['codename'] in {inventory['codename'], inventory['codename']+'-security', inventory['codename']+'-updates', inventory['codename']+'-backports'} for origin in row['origins']):
            raise ValueError('La versión candidata pertenece a otra distribución de Debian. No se permiten cambios de distribución desde este panel.')
        if pkg.installed and apt_pkg.version_compare(pkg.candidate.version, pkg.installed.version) <= 0:
            raise ValueError('No se permiten reinstalaciones ni retrocesos de versión.')
        row = dict(row, dependency=row['id'] not in selected_ids, new_install=not pkg.is_installed)
        changes.append(row)
    changes.sort(key=lambda row: row['id'])
    simulation = ''
    if changes:
        simulation = command(['/usr/bin/apt-get', '--simulate', *APT_OPTIONS, 'install', *specifications(changes)], timeout=80)
        validate_simulation(simulation, changes)
    download, required = cache.required_download, cache.required_space
    free = shutil.disk_usage('/').free
    if changes and free < download + max(0, required) + 512 * 1024 * 1024:
        raise ValueError('No hay espacio libre suficiente en / para descargar e instalar con margen de seguridad.')
    kernel = any(row['name'].startswith(('linux-image', 'linux-base', 'linux-headers')) for row in changes)
    if kernel and shutil.disk_usage('/boot').free < 200 * 1024 * 1024:
        raise ValueError('El espacio libre de /boot es insuficiente para un cambio de kernel.')
    # Include status and lists to invalidate approvals after APT or DPKG changes.
    files = [Path('/var/lib/dpkg/status'), *sorted(Path('/var/lib/apt/lists').glob('*Packages*')),
             *sorted(Path('/var/lib/apt/lists').glob('*InRelease'))]
    stamp = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.is_file()]
    fingerprint = hashlib.sha256(json.dumps([scope, [(r['id'], r['installed'], r['candidate']) for r in changes], stamp]).encode()).hexdigest()
    return {'scope': scope, 'fingerprint': fingerprint, 'changes': changes, 'download_bytes': download,
            'additional_space_bytes': required, 'root_free_bytes': free, 'kernel_update': kernel,
            'potential_services': impact([row['name'] for row in changes]), 'simulation': redact(simulation[-30000:]),
            'held_packages': [row['name'] for row in rows.values() if row['held']],
            'created_at': time.time(), 'expires_at': time.time() + 600}


def identifier(value):
    return str(uuid.UUID(str(value)))


@contextlib.contextmanager
def lock(name, blocking=False):
    import fcntl
    with (STATE / name).open('a') as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ValueError('Ya hay una tarea de actualizaciones en ejecución.')
        yield


def job_status():
    jobs = []
    for path in sorted((STATE / 'jobs').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        job = read(path, {})
        if job.get('state') in {'queued', 'running'} and time.time() - job.get('created_at', 0) > 20:
            unit = f"shc-updates-{job['id']}.service"
            result = subprocess.run(['/usr/bin/systemctl', 'is-active', unit], capture_output=True, text=True)
            if result.stdout.strip() not in {'active', 'activating', 'reloading'}:
                job.update(state='failed', phase='interrupted', error='La tarea se interrumpió. Revisá DPKG antes de reintentar.', ended_at=time.time())
                write(path, job)
        jobs.append(job)
    active = next((job for job in jobs if job.get('state') in {'queued', 'running'}), None)
    return {'active': active, 'jobs': jobs}


def queue_job(kind, plan=None):
    with lock('control.lock'):
        status = job_status()
        if status['active']:
            raise ValueError('Ya hay una tarea de actualizaciones en ejecución.')
        job = {'id': str(uuid.uuid4()), 'kind': kind, 'scope': plan['scope'] if plan else None,
               'state': 'queued', 'phase': 'queued', 'created_at': time.time(), 'plan_id': plan['id'] if plan else None}
        path = STATE / 'jobs' / f"{job['id']}.json"
        write(path, job)
        try:
            command(['/usr/bin/systemd-run', '--quiet', '--collect', '--service-type=exec',
                     f"--unit=shc-updates-{job['id']}", '--property=TimeoutStartSec=infinity',
                     HELPER, '--worker', job['id']])
        except Exception:
            job.update(state='failed', phase='launch-failed', error='No se pudo iniciar la tarea.', ended_at=time.time())
            write(path, job)
            raise
        return {'accepted': True, 'job_id': job['id']}


def install_command(plan):
    return ['/usr/bin/apt-get', '--assume-yes', *APT_OPTIONS, 'install', *specifications(plan['changes'])]


def run_worker(job_id):
    job_id = identifier(job_id)
    path = STATE / 'jobs' / f'{job_id}.json'
    job = read(path)
    if not job or job.get('state') != 'queued':
        raise ValueError('Tarea inválida o ya ejecutada.')
    def phase(value):
        job.update(phase=value, state='running');write(path, job)
    try:
        with lock('operation.lock'):
            phase('checking')
            with (STATE / 'jobs' / f'{job_id}.log').open('w') as log:
                if job['kind'] == 'refresh':
                    phase('refreshing-indexes')
                    args = ['/usr/bin/apt-get', '-o', 'APT::Update::Error-Mode=any', '-o', 'DPkg::Lock::Timeout=0', 'update']
                    result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, text=True, env=ENV, timeout=600)
                    if result.returncode:
                        raise ValueError('APT no pudo actualizar todos los índices. Revisá el registro; puede haber otro gestor activo o un repositorio sin conexión.')
                    phase('checking-security')
                    refresh_tracker()
                    write(CACHE / 'last-check.json', {'checked_at': time.time()})
                elif job['kind'] == 'install':
                    old = read(STATE / 'plans' / f"{identifier(job.get('plan_id'))}.json")
                    if not old:
                        raise ValueError('No existe el plan revisado de esta tarea.')
                    if time.time() > old['expires_at']:
                        raise ValueError('La simulación venció. Generá una nueva antes de instalar.')
                    new = build_plan(old['scope'])
                    if new['fingerprint'] != old['fingerprint']:
                        raise ValueError('Los paquetes o índices cambiaron desde la simulación. Volvé a revisar el plan.')
                    if not new['changes']:
                        raise ValueError('No hay cambios para instalar.')
                    backup = STATE / 'backups' / job_id
                    backup.mkdir(mode=0o700)
                    job['backup_directory'] = str(backup)
                    write(backup / 'plan.json', new)
                    (backup / 'packages.tsv').write_text(command(['/usr/bin/dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n']))
                    with tarfile.open(backup / 'configuration.tar.gz', 'w:gz') as archive:
                        for name in ['/etc/apt', '/etc/apache2', '/etc/libvirt', '/etc/ssh', '/etc/default', '/var/lib/dpkg/status', '/var/lib/apt/extended_states']:
                            if Path(name).exists():archive.add(name, recursive=True)
                    phase('installing')
                    # No timeout: never kill DPKG halfway through a transaction.
                    result = subprocess.run(install_command(new), stdout=log, stderr=subprocess.STDOUT, env=ENV)
                    if result.returncode:
                        raise ValueError('APT terminó con errores. No reintentes sin revisar el registro y el estado de DPKG.')
                else:
                    raise ValueError('Tipo de tarea no permitido.')
                phase('scanning')
                scan()
                job.update(state='succeeded', phase='finished', ended_at=time.time())
    except Exception as error:
        job.update(state='failed', phase='failed', error=redact(str(error))[:1600], ended_at=time.time())
        try:scan()
        except Exception:pass
    write(path, job)


def inventory(summary=False):
    data = read(CACHE / 'inventory.json', {'available': False, 'packages': [], 'security_count': 0, 'total_count': 0,
                                         'high_count': 0, 'reason': 'Todavía no se consultaron los índices. Usá Buscar actualizaciones.'})
    data.update(job_status())
    data['checked_at'] = read(CACHE / 'last-check.json', {}).get('checked_at')
    for job in data['jobs']:
        job.pop('plan', None)
    if summary:
        data.pop('packages', None)
    return data


def handle(request):
    action = request.get('action')
    if action in {'inventory', 'summary'}:
        return inventory(action == 'summary')
    if action == 'logs':
        job_id = identifier(request.get('job_id'))
        path = STATE / 'jobs' / f'{job_id}.log'
        try:
            with path.open('rb') as file:
                file.seek(max(0, path.stat().st_size - 60000));text = file.read().decode('utf-8', 'replace')
        except FileNotFoundError:text = 'La tarea aún no produjo salida.'
        return {'text': redact(text)}
    if action == 'changelog':
        name = request.get('package')
        row = next((row for row in inventory()['packages'] if row['id'] == name), None)
        if not row or not row['trusted']:
            raise ValueError('El paquete no pertenece al inventario de actualizaciones confiables.')
        return {'text': redact(command(['/usr/bin/apt-get', 'changelog', f"{row['id']}={row['candidate']}"], timeout=30)[-40000:])}
    if action == 'preview':
        if job_status()['active']:
            raise ValueError('Esperá a que termine la tarea actual.')
        plan = build_plan(request.get('scope'))
        plan['id'] = str(uuid.uuid4())
        write(STATE / 'plans' / f"{plan['id']}.json", plan)
        return plan
    if request.get('confirm') is not True:
        raise ValueError('Confirmación requerida.')
    if action == 'refresh':
        return queue_job('refresh')
    if action == 'apply':
        if request.get('acknowledge') is not True:
            raise ValueError('Confirmá el respaldo de datos y las posibles interrupciones de servicios.')
        plan_id = identifier(request.get('plan_id'))
        plan = read(STATE / 'plans' / f'{plan_id}.json')
        if not plan or time.time() > plan['expires_at']:
            raise ValueError('La simulación no existe o venció. Generá una nueva.')
        if not plan['changes']:
            raise ValueError('No hay actualizaciones aplicables en este plan.')
        # Revalidation happens inside the persistent worker before any install.
        return queue_job('install', plan)
    raise ValueError('Acción no permitida.')
