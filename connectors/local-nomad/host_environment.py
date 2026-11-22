"""Read-only observations from the caller's Linux namespaces and permissions."""
import http.client
import json
import os
import platform
import re
import socket
import stat
import subprocess
from pathlib import Path

DOCKER_SOCKET = Path("/var/run/docker.sock")
CONTROLLERS = {"cpu", "cpuset", "io", "memory", "pids"}
SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


def read_text(path):
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def kernel_info():
    system = platform.system()
    release = platform.release()
    kind = "unsupported"
    if system == "Linux":
        release = read_text(Path("/proc/sys/kernel/osrelease")) or release
        version = read_text(Path("/proc/version"))
        text = f"{release} {version}".lower()
        wsl2 = "microsoft-standard" in text or re.search(r"\bwsl[-_ ]?2\b", text)
        wsl1 = re.search(r"\bwsl[-_ ]?1\b|\b(?:3\.4|4\.4)\.0(?:-\d+)?-microsoft\b(?!-standard)", text)
        if not wsl1 and not wsl2 and "microsoft@microsoft.com" in text:
            wsl1 = re.search(r"\b(?:3\.4|4\.4)\.0\b", text)
        if wsl2 and not wsl1:
            kind = "wsl2"
        elif wsl1 and not wsl2:
            kind = "wsl1"
        elif ("wsl" in text or "microsoft" in release.lower() or "-microsoft" in version.lower()
              or "microsoft@microsoft.com" in text or os.path.isdir("/run/WSL")
              or os.path.isfile("/proc/sys/fs/binfmt_misc/WSLInterop")):
            kind = "wsl"
        else:
            kind = "native-linux" if release or version else "unknown"
    return {"platform": kind, "kernel_release": release, "architecture": platform.machine(), "hostname": platform.node()}


def unit_properties(name):
    """Query the local system manager, accepting a confirmed missing unit."""
    cmd = ["/usr/bin/systemctl", "--system", "show", "--all", name,
           "-p", "LoadState,ActiveState,FragmentPath,DropInPaths,MainPID"]
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True, capture_output=True, check=False,
                          env={"PATH": SYSTEM_PATH, "LC_ALL": "C"}, timeout=5)
    fields = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    if not fields.get("LoadState") or (proc.returncode and fields["LoadState"] != "not-found"):
        if any(reason in proc.stderr.lower() for reason in ("permission denied", "operation not permitted", "access denied")):
            raise PermissionError("Access to the systemd manager was denied")
        raise RuntimeError(f"Cannot inspect {name} through the systemd system manager")
    return fields


def systemd_info():
    result = {"pid1": read_text(Path("/proc/1/comm")) or None, "manager": "unreachable",
              "docker_unit_load": None, "docker_unit_active": None}
    try:
        unit = unit_properties("docker.service")
    except FileNotFoundError:
        result["manager"] = "systemctl-missing"
    except PermissionError:
        result["manager"] = "permission-denied"
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    else:
        result.update(manager="reachable", docker_unit_load=unit["LoadState"], docker_unit_active=unit.get("ActiveState"))
    result["ready"] = result["pid1"] == "systemd" and result["manager"] == "reachable"
    return result


def cgroup_info():
    try:
        available = set(Path("/sys/fs/cgroup/cgroup.controllers").read_text().split())
    except FileNotFoundError:
        state = "v2-unavailable"
    except OSError:
        state = "unreadable"
    else:
        missing = sorted(CONTROLLERS - available)
        return {"state": "v2", "controllers": sorted(available), "missing": missing, "ready": not missing}
    return {"state": state, "controllers": None, "missing": None, "ready": False}


def engine_info():
    # Connect before issuing the request and disable HTTPConnection's TCP fallback.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(DOCKER_SOCKET))
        conn = http.client.HTTPConnection("localhost")
        conn.auto_open = False
        conn.sock = sock
        conn.request("GET", "/info")
        with conn.getresponse() as response:
            if response.status in (401, 403):
                raise PermissionError("Docker Engine denied GET /info")
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Docker Engine /info response too large")
    info = json.loads(raw)
    if not isinstance(info, dict) or not isinstance(info.get("OSType"), str):
        raise TypeError("Invalid Docker Engine /info response")
    return info


def docker_info():
    result = {
        "endpoint": f"unix://{DOCKER_SOCKET}", "socket": "unknown", "daemon": "unreachable",
        "runtime": "unknown", "os_type": None, "cgroup_version": None, "rootless": None, "runc": None,
    }
    try:
        mode = DOCKER_SOCKET.stat().st_mode
        result["socket"] = "present" if stat.S_ISSOCK(mode) else "not-a-socket"
        if result["socket"] != "present":
            return result
        info = engine_info()
    except FileNotFoundError:
        result["socket"] = "missing"
    except PermissionError:
        result["daemon"] = "permission-denied"
    except (OSError, http.client.HTTPException):
        pass
    except (TypeError, RuntimeError, ValueError):
        result["daemon"] = "invalid-response"
    else:
        result.update(daemon="reachable", os_type=info["OSType"])
        operating_system = info.get("OperatingSystem")
        if isinstance(operating_system, str) and operating_system.lower().startswith("docker desktop"):
            result["runtime"] = "docker-desktop"
        elif info["OSType"] == "linux" and isinstance(operating_system, str) and operating_system:
            result["runtime"] = "linux-engine"
        if info.get("CgroupVersion"):
            result["cgroup_version"] = str(info["CgroupVersion"])
        if isinstance(info.get("Runtimes"), dict):
            result["runc"] = "runc" in info["Runtimes"]
        security = info.get("SecurityOptions")
        if "SecurityOptions" in info and (security is None or isinstance(security, list)):
            result["rootless"] = any("rootless" in str(option).lower() for option in security or [])
    return result


def detect_environment():
    result = kernel_info()
    if result["platform"] == "unsupported":
        return {**result, "systemd": None, "cgroups": None, "docker": None}
    return {**result, "systemd": systemd_info(), "cgroups": cgroup_info(), "docker": docker_info()}
