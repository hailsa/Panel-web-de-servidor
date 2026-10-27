#!/usr/bin/python3
"""Constrained, read-only journal queries for SHC. No caller-supplied CLI options."""
from datetime import datetime, timedelta, timezone
import json
import re
import subprocess
import sys

FIELDS = ['MESSAGE','PRIORITY','SYSLOG_IDENTIFIER','_SYSTEMD_UNIT','_SYSTEMD_USER_UNIT',
          '_COMM','_PID','_UID','_GID','_HOSTNAME','_BOOT_ID','_TRANSPORT',
          'CODE_FILE','CODE_LINE','CODE_FUNC','SYSLOG_FACILITY','_EXE',
          '__CURSOR','__REALTIME_TIMESTAMP']
RANGES = {'15m':15*60,'1h':3600,'6h':21600,'24h':86400,'7d':604800,'30d':2592000}


def run(*args):
    result = subprocess.run(['/usr/bin/journalctl','--no-pager','--quiet',*args],
                            capture_output=True,text=True,errors='replace',timeout=12,
                            env={'PATH':'/usr/bin:/bin','LC_ALL':'C','TZ':'UTC'})
    if result.returncode:
        raise ValueError('No se pudo consultar el journal. Revisá los filtros o la disponibilidad de los registros.')
    return result.stdout


def date(value):
    if not isinstance(value,str) or len(value)>40: raise ValueError('Fecha inválida')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('La fecha debe incluir zona horaria')
    return parsed.astimezone(timezone.utc)


def text(value,maximum=200):
    if not isinstance(value,str) or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError('Filtro de texto inválido')
    return value


def command(request):
    limit=int(request.get('limit',100))
    priority=int(request.get('priority',7))
    if not 20<=limit<=200 or not 0<=priority<=7:raise ValueError('Límite o prioridad inválidos')
    now=datetime.now(timezone.utc)
    until=date(request['until']) if request.get('until') else now
    kind=request.get('range','24h')
    if kind in RANGES:since=until-timedelta(seconds=RANGES[kind])
    elif kind=='custom':since=date(request.get('since'))
    elif kind=='boot':since=None
    else:raise ValueError('Período inválido')
    if since and (since>=until or until-since>timedelta(days=90)):
        raise ValueError('El período debe ser mayor que cero y no superar 90 días')
    args=['--output=json','--reverse','--lines=1001','--output-fields='+','.join(FIELDS),
          '--priority='+str(priority),'--until='+until.strftime('%Y-%m-%d %H:%M:%S.%f')]
    if since and not request.get('cursor'):args.append('--since='+since.strftime('%Y-%m-%d %H:%M:%S.%f'))
    boot=request.get('boot','')
    if kind=='boot' and not boot:boot='0'
    if boot:
        if boot not in {'0','-1'} and not re.fullmatch('[a-f0-9]{32}',boot):raise ValueError('Arranque inválido')
        args.append('--boot='+boot)
    unit=text(request.get('unit',''),180)
    if unit:
        if not re.fullmatch(r'[A-Za-z0-9_.:@\\-]+',unit):raise ValueError('Unidad inválida')
        args.append('--unit='+unit)
    identifier=text(request.get('identifier',''),128)
    if identifier:args.append('SYSLOG_IDENTIFIER='+identifier)
    kernel=request.get('kernel',False)
    if not isinstance(kernel,bool):raise ValueError('Filtro de kernel inválido')
    if kernel:args.append('_TRANSPORT=kernel')
    cursor=request.get('cursor','')
    if cursor:
        if not isinstance(cursor,str) or len(cursor)>512 or not re.fullmatch(r'[a-zA-Z0-9=;_-]+',cursor):raise ValueError('Cursor inválido')
        args.append('--cursor='+cursor)
    search=text(request.get('search',''),200).casefold()
    return args,limit,search,until.isoformat(),int(since.timestamp()*1000000) if since else None


def normalize(entry):
    result={}
    for key in FIELDS:
        value=entry.get(key)
        if isinstance(value,list):
            if all(isinstance(item,int) for item in value): value=bytes(value).decode('utf-8',errors='replace')
            else:value=' · '.join(str(item) for item in value)
        if value is not None:result[key]=str(value)[:16384 if key=='MESSAGE' else 1024]
    if not result.get('MESSAGE'):
        result['MESSAGE']='[Mensaje binario, vacío o demasiado extenso para esta vista]'
    result['PRIORITY']=result.get('PRIORITY','6')
    return result


def query(request):
    args,limit,search,until,lower_bound=command(request)
    records=[json.loads(line) for line in run(*args).splitlines() if line.strip()]
    cursor=request.get('cursor')
    entries=[]
    last=None
    scanned=0
    index=-1
    exhausted=False
    for index,entry in enumerate(records[:1000]):
        if entry.get('__CURSOR')==cursor:continue
        if lower_bound is not None and int(entry.get('__REALTIME_TIMESTAMP','0'))<lower_bound:
            exhausted=True
            break
        last=entry.get('__CURSOR')
        scanned+=1
        normalized=normalize(entry)
        if search and search not in ' '.join(normalized.get(field,'') for field in ['MESSAGE','SYSLOG_IDENTIFIER','_SYSTEMD_UNIT','_COMM','_PID']).casefold():continue
        entries.append(normalized)
        if len(entries)>=limit:break
    more=bool(last and index<len(records)-1 and not exhausted)
    return {'entries':entries,'next_cursor':last if more else None,'has_more':more,
            'scanned':scanned,'until':until,'order':'newest-first',
            'notice':'La búsqueda es literal y revisa hasta 1000 eventos por página. Podés continuar aunque no haya coincidencias.' if search else ''}


def metadata():
    boots=json.loads(run('--list-boots','--output=json','--reverse'))
    units=run('--field=_SYSTEMD_UNIT').splitlines()
    identifiers=run('--field=SYSLOG_IDENTIFIER').splitlines()
    return {'boots':boots[:50], 'units':sorted(set(units))[:500],
            'identifiers':sorted(set(identifiers))[:500],
            'storage':run('--disk-usage').strip(),'source':'systemd-journal'}


def handle(request):
    if request.get('action')=='metadata':return metadata()
    if request.get('action')=='query':return query(request)
    raise ValueError('Consulta no permitida')


if __name__=='__main__':
    try:
        raw=sys.stdin.read(16385)
        if len(raw)>16384:raise ValueError('Solicitud demasiado grande')
        request=json.loads(raw)
        if not isinstance(request,dict):raise ValueError('Solicitud inválida')
        print(json.dumps(handle(request)))
    except Exception as exc:
        print(json.dumps({'error':str(exc)[:400]}))
        sys.exit(1)
