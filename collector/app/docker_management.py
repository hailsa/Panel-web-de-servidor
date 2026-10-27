"""Docker management via fixed CLI operations, without exposing the Docker socket."""
import json
import re
import subprocess
import threading
import time
from fastapi import HTTPException

_cache = (0.0, None)
_lock = threading.Lock()
POLICIES = {'no', 'always', 'unless-stopped', 'on-failure'}


def docker(*arguments, timeout=15):
    try:
        result = subprocess.run(['docker', *arguments], text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise HTTPException(503, 'Docker no está disponible o tardó demasiado en responder')
    if result.returncode:
        raise HTTPException(409, result.stderr.strip()[:500] or 'Docker rechazó la operación')
    return result.stdout


def validate_id(value):
    if not re.fullmatch(r'[a-f0-9]{64}', value):
        raise HTTPException(400, 'Identificador de contenedor inválido')
    return value


def summary(item, stats=None):
    state, config, host = item.get('State', {}), item.get('Config', {}), item.get('HostConfig', {})
    labels = config.get('Labels') or {}
    ports=[]
    for destination, bindings in (item.get('NetworkSettings', {}).get('Ports') or {}).items():
        ports.append({'destination':destination, 'bindings':bindings or []})
    return {'id':item['Id'], 'name':item.get('Name','').lstrip('/'), 'image':config.get('Image',''),
            'state':state.get('Status','unknown'), 'health':state.get('Health',{}).get('Status','Sin healthcheck'),
            'started_at':state.get('StartedAt'), 'created_at':item.get('Created'),
            'restart_count':item.get('RestartCount',0), 'restart_policy':host.get('RestartPolicy',{}).get('Name','no'),
            'ports':ports, 'stats':stats or {}, 'compose_project':labels.get('com.docker.compose.project'),
            'compose_service':labels.get('com.docker.compose.service'),
            'protected':item.get('Name','').lstrip('/')=='shc-monitor'}


def stats_map():
    try:
        output=docker('stats','--no-stream','--no-trunc','--format','{{json .}}',timeout=8)
        return {item['ID']:item for item in (json.loads(line) for line in output.splitlines() if line)}
    except (HTTPException, ValueError):
        return {}


def json_lines(*arguments):
    return [json.loads(line) for line in docker(*arguments,'--format','{{json .}}').splitlines() if line]


def inventory():
    global _cache
    with _lock:
        if _cache[1] is not None and time.monotonic()-_cache[0]<5:
            return _cache[1]
        ids=docker('ps','-aq','--no-trunc').splitlines()
        stats=stats_map()
        items=json.loads(docker('inspect',*ids)) if ids else []
        info=json.loads(docker('info','--format','{{json .}}'))
        result={'containers':[summary(item,stats.get(item['Id'])) for item in items],
                'images':json_lines('image','ls','--no-trunc'), 'networks':json_lines('network','ls'),
                'volumes':json_lines('volume','ls'),
                'engine':{'version':info.get('ServerVersion'), 'cpus':info.get('NCPU'),
                          'memory_bytes':info.get('MemTotal'), 'driver':info.get('Driver')}}
        _cache=(time.monotonic(),result)
        return result


def detail(container_id):
    validate_id(container_id)
    item=json.loads(docker('inspect',container_id))[0]
    result=summary(item,stats_map().get(container_id))
    config, host, state=item.get('Config',{}),item.get('HostConfig',{}),item.get('State',{})
    result.update({'platform':item.get('Platform'), 'hostname':config.get('Hostname'),
        'user':config.get('User') or 'root (predeterminado)', 'working_dir':config.get('WorkingDir'),
        'memory_limit':host.get('Memory',0), 'cpu_limit':host.get('NanoCpus',0)/1e9,
        'privileged':host.get('Privileged',False), 'readonly_rootfs':host.get('ReadonlyRootfs',False),
        'network_mode':host.get('NetworkMode'), 'environment_keys':[entry.split('=',1)[0] for entry in config.get('Env') or []],
        'mounts':[{key:mount.get(key) for key in ('Type','Name','Source','Destination','RW','Propagation')} for mount in item.get('Mounts',[])],
        'networks':[{key:net.get(key) for key in ('IPAddress','GlobalIPv6Address','Gateway','MacAddress')} | {'name':name}
                    for name,net in (item.get('NetworkSettings',{}).get('Networks') or {}).items()],
        'exit_code':state.get('ExitCode'), 'oom_killed':state.get('OOMKilled',False),
        'processes':[], 'processes_reason':'El contenedor no está ejecutándose'})
    if result['state']=='running':
        try:
            # No command-line arguments: they can contain credentials.
            lines=docker('top',container_id,'-eo','pid,comm').splitlines()
            result['processes']=[line.split(None,1) for line in lines[1:101] if line.strip()]
            result['processes_reason']=''
        except HTTPException:
            result['processes_reason']='No se pudo consultar la lista de procesos'
    return result


def action(container_id, payload):
    global _cache
    validate_id(container_id)
    if payload.get('confirm') is not True:
        raise HTTPException(403,'Confirmación requerida')
    item=json.loads(docker('inspect',container_id))[0]
    name=item.get('Name','').lstrip('/')
    if name=='shc-monitor':
        raise HTTPException(409,'El propio panel se administra desde el host para mantener disponible esta sesión')
    operation=payload.get('action')
    state=item.get('State',{}).get('Status')
    allowed={'start':{'created','exited'},'stop':{'running'},'restart':{'running','exited'},
             'pause':{'running'},'unpause':{'paused'},'kill':{'running','paused'}}
    if operation=='restart-policy':
        policy=payload.get('policy')
        if policy not in POLICIES: raise HTTPException(400,'Política inválida')
        docker('update','--restart',policy,container_id)
    elif operation in allowed:
        if state not in allowed[operation]: raise HTTPException(409,'Acción incompatible con el estado actual')
        if operation=='kill' and payload.get('verify')!=name:
            raise HTTPException(403,'Escribí el nombre del contenedor para confirmar')
        docker(operation,container_id,timeout=45)
    else:
        raise HTTPException(400,'Acción no permitida')
    _cache=(0.0,None)
    import logging
    logging.getLogger('shc.docker').warning('Docker action=%s container=%s',operation,container_id)
    return {'accepted':True,'message':'Operación completada. Actualizando contenedor…'}


def logs(container_id):
    validate_id(container_id)
    try:
        result=subprocess.run(['docker','logs','--tail','200','--timestamps','--since','24h',container_id],
                              capture_output=True,text=True,errors='replace',timeout=8)
    except (OSError,subprocess.TimeoutExpired):
        raise HTTPException(503,'No se pudieron obtener los logs')
    if result.returncode: raise HTTPException(409,'El driver de logs no permite leer estos registros')
    return {'text':(result.stdout+result.stderr)[-131072:], 'limit':200}
