#!/usr/bin/python3
"""Narrow privileged boundary for SHC's KVM controls. JSON stdin/stdout only."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

URI = "qemu:///system"


def virsh(*args, timeout=12):
    result = subprocess.run(["/usr/bin/virsh", "-c", URI, *args], capture_output=True,
                            text=True, timeout=timeout, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise ValueError(result.stderr.strip()[:700] or "Error de libvirt")
    return result.stdout.strip()


def xml_for(domain):
    return ET.fromstring(virsh("dumpxml", "--domain", domain))


def optional(*args):
    try:
        return virsh(*args, timeout=5)
    except (ValueError, subprocess.TimeoutExpired):
        return ""


def fields(text):
    return dict(line.split(":", 1) for line in text.splitlines() if ":" in line)


def inventory(domain, detail=False):
    root = xml_for(domain)
    state = virsh("domstate", "--domain", domain).strip()
    info = {key.strip(): value.strip() for key, value in fields(virsh("dominfo", "--domain", domain)).items()}
    result = {"id": root.findtext("uuid"), "name": root.findtext("name"), "state": state,
              "vcpus": int(root.findtext("vcpu", "0")),
              "memory_bytes": int(root.findtext("memory", "0")) * 1024,
              "autostart": info.get("Autostart") == "enable",
              "persistent": info.get("Persistent") == "yes"}
    if not detail:
        return result
    result.update({"machine": root.find("os/type").get("machine", ""),
                   "architecture": root.find("os/type").get("arch", ""),
                   "firmware": "UEFI" if root.find("os/loader") is not None else "BIOS",
                   "cpu_mode": root.find("cpu").get("mode", "default") if root.find("cpu") is not None else "default",
                   "disks": [], "interfaces": [], "snapshots": [], "shares": [],
                   "watchdog": [], "vsock": False, "agent_configured": False,
                   "vnc": False, "guest_services": [],
                   "guest_services_reason": "Instalá y activá QEMU Guest Agent dentro del invitado para consultar servicios e IP."})
    inactive = ET.fromstring(virsh('dumpxml', '--domain', domain, '--inactive')) if result['persistent'] else None
    for disk in root.findall("devices/disk"):
        target, source, driver = disk.find("target"), disk.find("source"), disk.find("driver")
        name = target.get("dev", "") if target is not None else ""
        storage = {"target": name, "device": disk.get("device"),
                   "bus": target.get("bus") if target is not None else None,
                   "format": driver.get("type") if driver is not None else None,
                   "source": source.get('file', '') if disk.get('type') == 'file' and source is not None else next(iter(source.attrib.values()), "") if source is not None else "",
                   "readonly": disk.find("readonly") is not None}
        if disk.get('device') == 'cdrom':
            saved = media_disk(inactive, name) if inactive is not None else None
            storage['persistent_source'] = media_source(saved)
            storage['eject_reason'] = ('' if state in {'running', 'paused', 'shut off'} else 'Esperá a que la VM termine de cambiar de estado.')
            if result['persistent'] and saved is None:
                storage['eject_reason'] = 'Esta unidad no está definida para el próximo inicio. Administrala desde el hipervisor.'
            if disk.get('type') != 'file' or (saved is not None and saved.get('type') != 'file'):
                storage['eject_reason'] = 'Este medio no es una imagen de CD/DVD en archivo.'
            if not storage['source'] and not storage['persistent_source']:
                storage['eject_reason'] = 'La unidad de CD/DVD ya está vacía.'
            storage['can_eject'] = not bool(storage['eject_reason'])
        capacity = fields(optional("domblkinfo", "--domain", domain, name))
        for key in ("Capacity", "Allocation", "Physical"):
            value = capacity.get(key, "").strip()
            storage[key.lower()] = int(value) if value.isdigit() else None
        result["disks"].append(storage)
    from shc_vm_network import parse_addresses, interface_details
    addresses = []
    agent_configured = any(node.get('name') == 'org.qemu.guest_agent.0' for node in root.findall('devices/channel/target'))
    if state in {'running', 'paused'}:
        for source_type in ((['agent'] if agent_configured and state == 'running' else []) + ['lease', 'arp']):
            output = optional('domifaddr', '--domain', domain, '--full', '--source', source_type)
            addresses.extend(parse_addresses(output, source_type))
        from shc_vm_discovery import discover_addresses
        addresses.extend(discover_addresses(root, domain, addresses))
    for interface in root.findall("devices/interface"):
        result['interfaces'].append(interface_details(interface, addresses))
    for name in optional("snapshot-list", "--domain", domain, "--name").splitlines():
        if name:
            result["snapshots"].append({"name": name})
    for node in root.findall("devices/filesystem"):
        source, target = node.find("source"), node.find("target")
        result["shares"].append({"source": source.get("dir") if source is not None else None,
                                  "target": target.get("dir") if target is not None else None,
                                  "readonly": node.find("readonly") is not None})
    result["watchdog"] = [dict(node.attrib) for node in root.findall("devices/watchdog")]
    result["vsock"] = root.find("devices/vsock") is not None
    result["agent_configured"] = any(node.get("name") == "org.qemu.guest_agent.0" for node in root.findall("devices/channel/target"))
    result["vnc"] = root.find("devices/graphics[@type='vnc']") is not None
    stats = optional("domstats", domain, "--cpu-total", "--balloon")
    result["stats"] = dict(line.strip().split("=", 1) for line in stats.splitlines() if "=" in line)
    if result["agent_configured"] and state == "running":
        result["guest_services_reason"] = "El agente está configurado. La consulta de servicios requiere guest-exec habilitado."
        # Only a fixed read-only query; no command supplied by the browser is accepted.
        command = {"execute": "guest-exec", "arguments": {"path": "powershell.exe", "arg": ["-NoProfile", "-NonInteractive", "-Command", "Get-Service | Where-Object {$_.Status -eq 'Running'} | Select-Object Name,DisplayName | ConvertTo-Json -Compress"], "capture-output": True}}
        try:
            import base64
            import time
            response = json.loads(virsh("qemu-agent-command", "--domain", domain, json.dumps(command)))
            pid = response["return"]["pid"]
            for _ in range(8):
                time.sleep(0.25)
                status = json.loads(virsh("qemu-agent-command", "--domain", domain, json.dumps({"execute": "guest-exec-status", "arguments": {"pid": pid}})))["return"]
                if status.get("exited"):
                    if status.get("exitcode") == 0:
                        services = json.loads(base64.b64decode(status.get("out-data", "")).decode("utf-8-sig"))
                        result["guest_services"] = services if isinstance(services, list) else [services]
                        result["guest_services_reason"] = ""
                    break
        except (ValueError, KeyError, subprocess.TimeoutExpired):
            pass
    return result


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise ValueError("Nombre inválido; usá letras, números, guion y punto (máximo 64).")
    return value


def backup_config(domain, xml=None):
    backup = Path("/var/backups/shc-monitor/vm-config")
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S%f")
    path = backup / f"{domain}-{stamp}.xml"
    path.write_text(xml if xml is not None else virsh("dumpxml", "--domain", domain, "--inactive"))
    path.chmod(0o600)
    return path


def save_config(domain, root):
    if virsh("domstate", "--domain", domain) != "shut off":
        raise ValueError("Apagá la VM antes de cambiar sus dispositivos o recursos.")
    backup_config(domain)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml") as file:
        file.write(ET.tostring(root, encoding="unicode")); file.flush()
        virsh("define", file.name, "--validate")


def media_disk(root, target):
    if root is None:
        return None
    return next((node for node in root.findall('devices/disk')
                 if node.find('target') is not None and node.find('target').get('dev') == target), None)


def media_source(node):
    source = node.find('source') if node is not None else None
    return source.get('file', '') if source is not None else ''


def eject_media(domain, root, state, request):
    target = request.get('target')
    if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,15}', target):
        raise ValueError('Unidad de CD/DVD inválida.')
    if state not in {'running', 'paused', 'shut off'}:
        raise ValueError('Esperá a que la VM termine de cambiar de estado.')
    info = {key.strip(): value.strip() for key, value in fields(virsh('dominfo', '--domain', domain)).items()}
    persistent = info.get('Persistent') == 'yes'
    saved_xml = virsh('dumpxml', '--domain', domain, '--inactive') if persistent else None
    saved = media_disk(ET.fromstring(saved_xml), target) if persistent else None
    current = media_disk(root, target)
    for disk in [current] + ([saved] if persistent else []):
        if disk is None or disk.get('device') != 'cdrom' or disk.get('type') != 'file':
            raise ValueError('Sólo se permite expulsar una imagen de CD/DVD; los discos de datos no se pueden quitar con esta acción.')
    source, saved_source = media_source(current), media_source(saved)
    if request.get('expected_source') != source or request.get('expected_persistent_source') != saved_source:
        raise ValueError('El medio montado cambió. Actualizá la vista y volvé a confirmar.')
    live = state in {'running', 'paused'} and bool(source)
    config = persistent and bool(saved_source)
    if not live and not config:
        raise ValueError('La unidad de CD/DVD ya está vacía.')
    if persistent:
        backup_config(domain, saved_xml)
    flags = (['--live'] if live else []) + (['--config'] if config else [])
    try:
        virsh('change-media', '--domain', domain, '--path', target, '--eject', *flags, timeout=25)
    except ValueError as error:
        raise ValueError(f'No se pudo completar la expulsión. Si el invitado mantiene el CD/DVD bloqueado, apagá la VM y reintentá. Revisá el estado actual y el próximo inicio. Detalle: {error}') from error
    if live and media_source(media_disk(xml_for(domain), target)):
        raise ValueError('El invitado todavía no liberó el CD/DVD. Revisá el estado y reintentá con la VM apagada.')
    if config and media_source(media_disk(ET.fromstring(virsh('dumpxml', '--domain', domain, '--inactive')), target)):
        raise ValueError('No se confirmó la expulsión para el próximo inicio. Actualizá la vista y reintentá.')
    return ('ISO expulsada de la unidad de CD/DVD y de la configuración del próximo inicio. El archivo se conserva en el servidor.'
            if persistent else 'ISO expulsada de la unidad de CD/DVD. El archivo se conserva en el servidor.')


def handle(request):
    action = request.get("action")
    if action == 'network-options':
        from shc_vm_network import network_options
        return network_options(virsh)
    if action in {'create-options','create-preview','create','browse-isos'}:
        from shc_vm_create import creation_options, preview, create, browse_isos
        if action=='browse-isos':return browse_isos(request)
        if action=='create-options':return creation_options()
        if action=='create-preview':return preview(request)
        return create(request)
    if action == "list":
        return {"available": True, "machines": [inventory(item) for item in virsh("list", "--all", "--uuid").splitlines() if item]}
    domain = str(uuid.UUID(request.get("id", "")))
    root = xml_for(domain)
    if action == "detail":
        return inventory(domain, True)
    if action == "console":
        graphics = root.find("devices/graphics[@type='vnc']")
        if graphics is None:
            raise ValueError("Esta VM no tiene una consola VNC configurada.")
        port = int(graphics.get("port", "-1"))
        address = graphics.get("listen") or (graphics.find("listen").get("address") if graphics.find("listen") is not None else "")
        if address not in {"127.0.0.1", "::1"} or not 5900 <= port <= 65535:
            raise ValueError("La consola debe escuchar en loopback y la VM estar encendida.")
        return {"port": port, "host": address}
    if request.get("confirm") is not True:
        raise ValueError("Confirmación requerida")
    state = virsh("domstate", "--domain", domain)
    commands = {"start": ("start", {"shut off"}), "shutdown": ("shutdown", {"running", "paused"}),
                "reboot": ("reboot", {"running"}), "pause": ("suspend", {"running"}),
                "resume": ("resume", {"paused"}), "force-off": ("destroy", {"running", "paused"}),
                "reset": ("reset", {"running"})}
    if action in commands:
        command, allowed = commands[action]
        if state not in allowed:
            raise ValueError("Acción incompatible con el estado actual de la VM.")
        virsh(command, "--domain", domain)
    elif action == 'media-eject':
        media_message = eject_media(domain, root, state, request)
    elif action == "autostart":
        if not isinstance(request.get("enabled"), bool):
            raise ValueError("Valor inválido")
        virsh("autostart", "--domain", domain, *([] if request["enabled"] else ["--disable"]))
    elif action in {"snapshot-create", "snapshot-revert", "snapshot-delete"}:
        name = safe_name(request.get("name"))
        if state != "shut off":
            raise ValueError("Para estas instantáneas, apagá primero la VM. No se guardará RAM.")
        if action == "snapshot-create":
            snapshot = ET.Element("domainsnapshot")
            ET.SubElement(snapshot, "name").text = name
            ET.SubElement(snapshot, "memory", snapshot="no")
            disks = ET.SubElement(snapshot, "disks")
            for disk in root.findall("devices/disk"):
                target, driver = disk.find("target"), disk.find("driver")
                if target is None:
                    continue
                writable = disk.get("device") == "disk" and disk.find("readonly") is None
                if writable and (driver is None or driver.get("type") != "qcow2"):
                    raise ValueError("Las instantáneas internas requieren todos los discos de datos en qcow2.")
                ET.SubElement(disks, "disk", name=target.get("dev"), snapshot="internal" if writable else "no")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".xml") as file:
                file.write(ET.tostring(snapshot, encoding="unicode")); file.flush()
                virsh("snapshot-create", "--domain", domain, file.name, "--atomic", timeout=90)
        else:
            virsh("snapshot-revert" if action.endswith("revert") else "snapshot-delete", "--domain", domain, "--snapshotname", name, timeout=90)
    elif action in {'network-edit', 'network-add'}:
        if state != 'shut off':
            raise ValueError('Apagá la VM antes de modificar sus interfaces de red. No se apagará automáticamente.')
        from shc_vm_network import network_options, configure_interface
        root = ET.fromstring(virsh('dumpxml', '--domain', domain, '--inactive'))
        updated = configure_interface(root, request, network_options(virsh))
        new_macs = {node.find('mac').get('address').lower() for node in updated.findall('devices/interface') if node.find('mac') is not None}
        for other in virsh('list', '--all', '--uuid').splitlines():
            if other == domain:
                continue
            other_root = ET.fromstring(virsh('dumpxml', '--domain', str(uuid.UUID(other)), '--inactive'))
            if any(node.get('address', '').lower() in new_macs for node in other_root.findall('devices/interface/mac')):
                raise ValueError('Una de las direcciones MAC ya está asignada a otra VM.')
        save_config(domain, updated)
    elif action in {"watchdog", "vsock", "agent", "share", "resources"}:
        root = ET.fromstring(virsh("dumpxml", "--domain", domain, "--inactive"))
        devices = root.find("devices")
        if action == "watchdog":
            if devices.find("watchdog") is not None:
                raise ValueError("Ya existe un watchdog.")
            ET.SubElement(devices, "watchdog", model="itco", action="reset")
        elif action == "vsock":
            if devices.find("vsock") is not None:
                raise ValueError("Ya existe un dispositivo vsock.")
            ET.SubElement(ET.SubElement(devices, "vsock", model="virtio"), "cid", auto="yes")
        elif action == "agent":
            if any(t.get("name") == "org.qemu.guest_agent.0" for t in devices.findall("channel/target")):
                raise ValueError("El canal del agente ya existe.")
            channel = ET.SubElement(devices, "channel", type="unix")
            ET.SubElement(channel, "target", type="virtio", name="org.qemu.guest_agent.0")
        elif action == "resources":
            cpus, memory = int(request.get("cpus", 0)), int(request.get("memory_mib", 0))
            host_mib = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // 1048576
            if not 1 <= cpus <= (os.cpu_count() or 1) or not 256 <= memory <= host_mib:
                raise ValueError("Recursos fuera del rango permitido.")
            root.find("vcpu").text = str(cpus)
            root.find("vcpu").attrib.pop("current", None)
            for node in [root.find("memory"), root.find("currentMemory")]:
                if node is not None:
                    node.set("unit", "KiB"); node.text = str(memory * 1024)
            topology = root.find("cpu/topology")
            if topology is not None:
                topology.set("sockets", "1"); topology.set("cores", str(cpus)); topology.set("threads", "1")
                topology.attrib.pop("dies", None); topology.attrib.pop("clusters", None)
        else:
            name = safe_name(request.get("name"))
            directory = Path("/srv/shc-shares") / name
            if not directory.is_dir() or directory.is_symlink() or directory.resolve().parent != Path("/srv/shc-shares"):
                raise ValueError("El directorio debe existir previamente en /srv/shc-shares y no ser un enlace.")
            if any(t.get("dir") == name for t in devices.findall("filesystem/target")):
                raise ValueError("Ya existe un recurso compartido con ese nombre.")
            if not Path("/usr/libexec/virtiofsd").exists() and not Path("/usr/lib/qemu/virtiofsd").exists():
                raise ValueError("El host necesita virtiofsd instalado para compartir directorios.")
            backing = root.find("memoryBacking")
            if backing is None: backing = ET.SubElement(root, "memoryBacking")
            for child in list(backing):
                if child.tag in {"source", "access"}: backing.remove(child)
            ET.SubElement(backing, "source", type="memfd")
            ET.SubElement(backing, "access", mode="shared")
            share = ET.SubElement(devices, "filesystem", type="mount", accessmode="passthrough")
            ET.SubElement(share, "driver", type="virtiofs")
            ET.SubElement(share, "source", dir=str(directory))
            ET.SubElement(share, "target", dir=name)
            if request.get("readonly", True): ET.SubElement(share, "readonly")
        save_config(domain, root)
    else:
        raise ValueError("Acción no permitida")
    import syslog
    syslog.syslog(syslog.LOG_NOTICE, f"SHC VM action={action} domain={domain}")
    return {"accepted": True, "message": media_message if action == 'media-eject' else "Solicitud enviada a libvirt. Actualizando estado…"}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384: raise ValueError("Solicitud demasiado grande")
        request = json.loads(raw)
        if not isinstance(request, dict): raise ValueError("Solicitud inválida")
        print(json.dumps(handle(request)))
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:700]}))
        sys.exit(1)
