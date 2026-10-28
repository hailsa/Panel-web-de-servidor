"""KVM creation through validated choices and new libvirt volumes only."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET

ROOT = Path('/var/lib/libvirt/images')
BOOT = Path('/var/lib/libvirt/boot')
STATE = Path('/run/shc-vm-creator')


def virsh(*args):
    result=subprocess.run(['/usr/bin/virsh','-c','qemu:///system',*args],text=True,capture_output=True,
                          timeout=30,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    if result.returncode:raise ValueError(result.stderr.strip()[:500] or 'Libvirt rechazó la solicitud')
    return result.stdout.strip()


def host_memory():
    values={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
    return values


def safe_directory(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():return False
    if not path.resolve().is_relative_to(ROOT):return False
    for node in [path,*path.parents]:
        info=node.stat()
        if info.st_uid!=0 or info.st_mode & 0o022:return False
        if node==ROOT:break
    return ',' not in str(path)


def creation_options():
    memory=host_memory()
    pools=[]
    for pool_id in virsh('pool-list','--uuid').splitlines():
        root=ET.fromstring(virsh('pool-dumpxml',pool_id))
        path=root.findtext('target/path','')
        if root.get('type')!='dir' or not safe_directory(path):continue
        space=shutil.disk_usage(path)
        pools.append({'id':pool_id,'name':root.findtext('name'),'path':path,'free_bytes':space.free})
    networks=[]
    for net_id in virsh('net-list','--uuid').splitlines():
        root=ET.fromstring(virsh('net-dumpxml',net_id))
        name=root.findtext('name','')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',name):continue
        forward=root.find('forward')
        networks.append({'id':net_id,'name':name,'mode':forward.get('mode') if forward is not None else 'isolated'})
    isos={}
    scanned=0
    for base in (ROOT,BOOT):
        if not base.is_dir():continue
        for current,dirs,files in os.walk(base,followlinks=False):
            dirs[:]=[name for name in dirs if not (Path(current)/name).is_symlink() and len((Path(current)/name).relative_to(base).parts)<=4]
            for name in files:
                scanned+=1
                path=Path(current)/name
                if scanned>3000:break
                if name.lower().endswith('.iso') and not path.is_symlink() and path.is_file() and ',' not in str(path):
                    isos[str(path)]={'path':str(path),'name':name,'size_bytes':path.stat().st_size}
            if scanned>3000:break
    return {'ready':bool(pools) and Path('/usr/bin/virt-install').exists(),
            'cpus':os.cpu_count() or 1,'memory_total_mib':memory['MemTotal']//1048576,
            'memory_available_mib':memory['MemAvailable']//1048576,
            'reserve_mib':1024,'pools':pools,'networks':networks,
            'isos':list(isos.values())[:200],
            'uefi':Path('/usr/share/OVMF/OVMF_CODE_4M.fd').exists(),
            'tpm':shutil.which('swtpm') is not None}


def boolean(payload,name,default=False):
    value=payload.get(name,default)
    if not isinstance(value,bool):raise ValueError('Valor inválido: '+name)
    return value


def validate(payload,options):
    if not options['ready']:raise ValueError('El host necesita virt-install y un pool de directorios disponible bajo /var/lib/libvirt/images')
    name=payload.get('name','')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,62}',name):
        raise ValueError('Nombre inválido: usá hasta 63 letras, números, guion o guion bajo')
    request_id=str(uuid.UUID(payload.get('request_id','')))
    profile=payload.get('profile','linux')
    if profile not in {'linux','windows','generic'}:raise ValueError('Perfil de sistema inválido')
    firmware=payload.get('firmware','uefi')
    if firmware not in {'bios','uefi'} or firmware=='uefi' and not options['uefi']:raise ValueError('Firmware no disponible')
    cpus,memory,disk=int(payload.get('cpus',0)),int(payload.get('memory_mib',0)),int(payload.get('disk_gib',0))
    if not 1<=cpus<=options['cpus']:raise ValueError('La CPU solicitada supera los núcleos disponibles del host')
    if not 512<=memory<=options['memory_total_mib']-options['reserve_mib']:raise ValueError('La memoria debe reservar al menos 1 GiB para el host')
    if not 2<=disk<=16384:raise ValueError('Disco fuera de rango (2–16384 GiB)')
    pool=next((item for item in options['pools'] if item['id']==payload.get('pool')),None)
    if pool is None:raise ValueError('Pool de almacenamiento inválido')
    if disk*1073741824>pool['free_bytes']-2147483648:raise ValueError('No hay espacio libre suficiente; se reservan 2 GiB de margen')
    network=None
    if payload.get('network'):
        network=next((item for item in options['networks'] if item['id']==payload['network']),None)
        if network is None:raise ValueError('La red seleccionada no está activa')
    iso_paths={item['path'] for item in options['isos']}
    iso,drivers=payload.get('iso',''),payload.get('drivers_iso','')
    if iso and iso not in iso_paths or drivers and drivers not in iso_paths:raise ValueError('Elegí una ISO existente de la biblioteca permitida')
    tpm=boolean(payload,'tpm')
    secure_boot=boolean(payload,'secure_boot')
    if tpm and (not options['tpm'] or firmware!='uefi'):raise ValueError('TPM 2.0 necesita UEFI y swtpm en el host')
    if secure_boot and firmware!='uefi':raise ValueError('Secure Boot requiere UEFI')
    start=boolean(payload,'start')
    if start and memory>options['memory_available_mib']-options['reserve_mib']:
        raise ValueError('La memoria disponible no alcanza para encenderla ahora. Podés crearla apagada.')
    return {'name':name,'id':request_id,'profile':profile,'firmware':firmware,'cpus':cpus,'memory_mib':memory,
            'disk_gib':disk,'pool':pool,'network':network,'iso':iso,'drivers_iso':drivers,
            'disk_bus':'sata' if profile=='windows' else 'virtio',
            'network_model':'e1000e' if profile=='windows' else 'virtio',
            'autostart':boolean(payload,'autostart'),'agent':boolean(payload,'agent',True),
            'tpm':tpm,'secure_boot':secure_boot,'start':start}


def disk_path(plan):
    return str(Path(plan['pool']['path'])/(plan['name']+'-'+plan['id'][:8]+'.qcow2'))


def generate_xml(plan):
    boot=('uefi,' if plan['firmware']=='uefi' else '')+'cdrom,hd,menu=on'
    if plan['secure_boot']:
        boot+=',firmware.feature0.name=secure-boot,firmware.feature0.enabled=yes,firmware.feature1.name=enrolled-keys,firmware.feature1.enabled=yes'
    command=['/usr/bin/virt-install','--connect','qemu:///system','--name',plan['name'],'--uuid',plan['id'],
             '--memory',str(plan['memory_mib']),'--vcpus',str(plan['cpus']),'--cpu','host-passthrough',
             '--machine','q35','--osinfo','generic','--import','--boot',boot,
             '--disk',f"path={disk_path(plan)},size={plan['disk_gib']},format=qcow2,bus={plan['disk_bus']}",
             '--network',f"network={plan['network']['name']},model={plan['network_model']}" if plan['network'] else 'none',
             '--graphics','vnc,listen=127.0.0.1','--video','vga','--noautoconsole','--print-xml','--dry-run']
    for iso in [plan['iso'],plan['drivers_iso']]:
        if iso:command+=['--disk',f'path={iso},device=cdrom,bus=sata,readonly=on']
    if plan['agent']:command+=['--channel','unix,target.type=virtio,target.name=org.qemu.guest_agent.0']
    if plan['tpm']:command+=['--tpm','backend.type=emulator,backend.version=2.0,model=tpm-crb']
    result=subprocess.run(command,text=True,capture_output=True,timeout=30,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    if result.returncode:raise ValueError(result.stderr.strip()[:600] or 'No se pudo generar la configuración KVM')
    root=ET.fromstring(result.stdout)
    if root.findtext('uuid')!=plan['id'] or root.findtext('name')!=plan['name']:raise ValueError('La configuración generada no coincide')
    if plan['profile']=='windows':
        clock=root.find('clock')
        if clock is not None:clock.set('offset','localtime')
    return ET.tostring(root,encoding='unicode')


def ensure_unused(plan):
    if plan['name'] in virsh('list','--all','--name').splitlines():raise ValueError('Ya existe una máquina con ese nombre')
    if plan['id'] in virsh('list','--all','--uuid').splitlines():raise ValueError('El identificador ya pertenece a una VM')
    if os.path.lexists(disk_path(plan)):raise ValueError('El disco de destino ya existe y no se sobrescribirá')


def preview(payload):
    plan=validate(payload,creation_options())
    ensure_unused(plan)
    generate_xml(plan)
    warnings=[]
    if not plan['iso']:warnings.append('No hay ISO de instalación: se creará un disco vacío y tendrás que conectar un medio antes de instalar el sistema.')
    if plan['memory_mib']>host_memory()['MemAvailable']//1048576-1024:warnings.append('La RAM disponible no alcanza para encenderla ahora; se guardará apagada.')
    if plan['profile']=='windows':warnings.append('El perfil Windows usa disco SATA y red e1000e para facilitar la instalación. Guest Agent requiere instalación dentro de Windows.')
    warnings.append('El disco qcow2 crecerá a medida que se use hasta su capacidad máxima. Controlá el espacio libre del host.')
    return {'plan':plan,'disk_path':disk_path(plan),'warnings':warnings}


def create(payload):
    if payload.get('confirm') is not True:raise ValueError('Confirmación requerida')
    request_id=str(uuid.UUID(payload.get('request_id','')))
    STATE.mkdir(mode=0o700,exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_uid!=0:raise ValueError('Directorio de control inválido')
    lockfd=os.open(STATE/'lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Hay otra creación en curso; esperá unos segundos')
        record=STATE/(request_id+'.json')
        fingerprint=hashlib.sha256(json.dumps({key:value for key,value in payload.items() if key not in {'action','confirm'}},sort_keys=True).encode()).hexdigest()
        if record.exists():
            previous=json.loads(record.read_text())
            if previous['fingerprint']!=fingerprint:raise ValueError('Esta solicitud ya se usó con otra configuración')
            return previous['result']
        plan=validate(payload,creation_options())
        ensure_unused(plan)
        xml=generate_xml(plan)
        volume=Path(disk_path(plan)).name
        backup=Path('/var/backups/shc-monitor/vm-created')
        backup.mkdir(mode=0o700,parents=True,exist_ok=True)
        config=backup/(plan['id']+'.xml')
        config.write_text(xml);config.chmod(0o600)
        virsh('vol-create-as',plan['pool']['id'],volume,str(plan['disk_gib']*1073741824),'--format','qcow2','--allocation','0')
        actual=virsh('vol-path','--pool',plan['pool']['id'],volume)
        if Path(actual).resolve()!=Path(disk_path(plan)).resolve():raise ValueError('La ruta del volumen creado no coincide; se conservó el volumen para revisión')
        try:
            with tempfile.NamedTemporaryFile(mode='w',suffix='.xml') as file:
                file.write(xml);file.flush();virsh('define',file.name,'--validate')
        except Exception as exc:
            raise ValueError(f'No se definió la VM; el disco nuevo {volume} se conservó para revisión. {exc}')
        warnings=[]
        if plan['autostart']:
            try:virsh('autostart','--domain',plan['id'])
            except ValueError:warnings.append('La VM se creó, pero no se pudo activar el autoinicio.')
        started=False
        if plan['start']:
            try:virsh('start','--domain',plan['id']);started=True
            except ValueError as exc:warnings.append('La VM se creó apagada; no pudo iniciarse: '+str(exc))
        result={'accepted':True,'id':plan['id'],'name':plan['name'],'started':started,'warnings':warnings,
                'message':'Máquina virtual creada. Podés abrir su ficha y la consola VNC.'}
        record.write_text(json.dumps({'fingerprint':fingerprint,'result':result}));record.chmod(0o600)
        import syslog
        syslog.syslog(syslog.LOG_NOTICE,f"SHC VM created domain={plan['id']} name={plan['name']}")
        return result
    finally:
        os.close(lockfd)
