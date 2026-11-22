#!/usr/bin/python3 -ISB
"""Provision the catalog's single-host Nomad service from a trusted catalog checkout."""
import argparse
import ctypes
import fcntl
import http.client
import json
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

PROJECT = Path(__file__).resolve().parent
# Isolated Python has no script directory or PYTHONPATH on its import path.
sys.path.extend([str(PROJECT), str(PROJECT.parents[1] / "connectors" / "local-nomad")])
from host_environment import SYSTEM_PATH, detect_environment, unit_properties
from nomad_api import (
    NAMESPACE,
    PEER,
    POLICY,
    ROOT,
    Api,
    ApiError,
    ready,
    secret_file,
    until,
)
from release import VERSION, install_binary, sha256

UNIT = Path("/etc/systemd/system/catalog-nomad.service")
PRIVATE = ROOT / "private"
CONNECTOR = ROOT / "connector"
RULES = f'''namespace "{NAMESPACE}" {{
  capabilities = ["plan-job", "register-job", "purge-job", "read-job", "read-logs"]
}}
node {{
  policy = "read"
}}
'''
CLIENT_FILES = ("nomad-agent-ca.pem", "global-cli-nomad.pem", "global-cli-nomad-key.pem")
FOREIGN_PATHS = ("/etc/nomad.d", "/etc/nomad", "/opt/nomad", "/var/lib/nomad")


def run(args, **kwargs):
    if "input" not in kwargs:
        kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def check_ports():
    for kind, port in ((socket.SOCK_STREAM, 4646), (socket.SOCK_STREAM, 4647),
                       (socket.SOCK_STREAM, 4648), (socket.SOCK_DGRAM, 4648)):
        with socket.socket(socket.AF_INET, kind) as sock:
            # Ignore old TCP TIME_WAIT sockets after a clean shutdown.
            if kind == socket.SOCK_STREAM:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                if kind == socket.SOCK_STREAM:
                    sock.listen()
            except OSError as exc:
                raise RuntimeError(f"Local port {port} is occupied or unavailable") from exc


def check_host():
    if os.geteuid() != 0:
        raise RuntimeError("Dispatch installer checks through the root deployment worker")
    environment = detect_environment()
    host = environment["platform"]
    if host == "wsl1":
        raise RuntimeError("WSL1 cannot run this Nomad client. From Windows, confirm the distro with "
                           "wsl --list --verbose and convert it with wsl --set-version <Distro> 2")
    if host == "unsupported" or environment["architecture"] != "x86_64":
        raise RuntimeError("The packaged Nomad binary requires x86-64 Linux")
    systemd = environment["systemd"]
    if not systemd["ready"]:
        message = (f"{host}: systemd requires PID 1 and a reachable system manager "
                   f"(PID 1: {systemd['pid1']}, manager: {systemd['manager']}). "
                   "Run the root worker in the host's systemd namespace.")
        if host in ("wsl2", "wsl"):
            message += (" In the WSL distro, check [boot] systemd=true in /etc/wsl.conf "
                        "and restart the distribution after enabling it.")
        raise RuntimeError(message)
    cgroups = environment["cgroups"]
    if not cgroups["ready"]:
        detail = ", ".join(cgroups["missing"] or []) or cgroups["state"]
        raise RuntimeError(f"{host}: required cgroup v2 controllers unavailable: {detail}")
    if not shutil.which("gpg"):
        raise RuntimeError("Missing command: gpg")
    docker = environment["docker"]
    if docker["daemon"] != "reachable":
        message = (f"{host}: cannot query Docker Engine at {docker['endpoint']} "
                   f"(socket: {docker['socket']}, daemon: {docker['daemon']}). ")
        if host in ("wsl2", "wsl"):
            message += "If using Docker Desktop, check its Linux engine and this distro's WSL integration."
        else:
            message += "Check the configured local Docker Engine and the worker's socket access."
        raise RuntimeError(message)
    if docker["os_type"] != "linux" or docker["cgroup_version"] != "2" or docker["rootless"] is not False:
        raise RuntimeError("Docker /info must confirm a rootful Linux Docker daemon with cgroup v2")
    if docker["runc"] is not True:
        raise RuntimeError("Docker must provide the runc runtime")
    if unit_properties("nomad.service")["LoadState"] != "not-found":
        raise RuntimeError("Existing nomad.service found. Resolve ownership before installation")
    for path in FOREIGN_PATHS:
        if os.path.lexists(path):
            raise RuntimeError(f"Existing Nomad path {path}. Inspect the unmanaged deployment")
    return environment


def managed_install(uid):
    if not os.path.lexists(ROOT):
        return None
    info = ROOT.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError(f"Unsafe or unmanaged installation at {ROOT}")
    for directory in (PRIVATE, CONNECTOR):
        if not os.path.lexists(directory):
            raise RuntimeError(f"Missing managed directory at {directory}")
        entry = directory.lstat()
        forbidden = 0o077 if directory == PRIVATE else 0o022
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_mode & forbidden:
            raise RuntimeError(f"Unsafe or unmanaged directory at {directory}")
    marker = PRIVATE / "install.json"
    if not marker.is_file():
        raise RuntimeError(f"Missing catalog ownership record at {ROOT}")
    record = json.loads(marker.read_text())
    if record.get("format") != 1 or record.get("uid") != uid or record.get("version") != VERSION:
        raise RuntimeError("Installation owner or release differs. Inspect the managed installation")
    for name in ("nomad", "agent.hcl"):
        if record[name] != sha256(PRIVATE / name):
            raise RuntimeError(f"Installed {name} differs from the ownership record")
    check_private_state(PRIVATE)
    return record


def check_private_state(directory):
    secret_file(directory / "management.token")
    for name in (*CLIENT_FILES, "global-server-nomad.pem", "global-server-nomad-key.pem", "nomad-agent-ca-key.pem"):
        if not (directory / name).is_file():
            raise RuntimeError(f"Missing private TLS file {name}. Restore the matching backup")
    if not (directory / "bootstrap.pending").exists():
        raft = directory / "data/server/raft/raft.db"
        if not raft.is_file() or raft.stat().st_size == 0:
            raise RuntimeError("Missing managed Raft database. Restore the matching cluster backup")


def check_other_agents(managed_pid, proc=Path("/proc")):
    for process in proc.iterdir():
        if not process.name.isdecimal() or process.name == managed_pid:
            continue
        try:
            if not (process / "comm").read_text(errors="replace").startswith("nomad"):
                continue
            argv = (process / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, ProcessLookupError):
            continue  # Process exited between listing and inspection.
        if argv[1:2] == [b"agent"]:
            raise RuntimeError(f"Unmanaged Nomad agent PID {process.name}. Inspect its deployment")


def check_unit(record):
    props = unit_properties(UNIT.name)
    exists = os.path.lexists(UNIT)
    if (props.get("DropInPaths") or props.get("FragmentPath", "") not in ("", str(UNIT))
            or props["LoadState"] not in ("loaded", "not-found")):
        raise RuntimeError("An unmanaged unit, override or mask is present")
    if exists:
        entry = UNIT.lstat()
        # check_host requires this process to be root. Verify permissions before trusting the contents.
        if (record is None or not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
                or entry.st_mode & 0o022 or UNIT.read_bytes() != (PROJECT / UNIT.name).read_bytes()):
            raise RuntimeError(f"Refusing to replace existing unit {UNIT}")
    elif props["LoadState"] != "not-found":
        raise RuntimeError("Loaded unit has no managed file on disk")
    if props.get("ActiveState") not in ("active", "inactive", "failed"):
        raise RuntimeError("Wait for the unit's current state transition to finish")
    if props.get("ActiveState") != "active":
        check_ports()
    elif not exists:
        raise RuntimeError("Active service has no owned unit file")
    check_other_agents(props.get("MainPID", "0") if exists and record else "0")
    return exists


def sync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prepare(uid):
    # Commit the package marker, credentials and verified binary together.
    with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix=".catalog-nomad-") as temp:
        stage = Path(temp) / "stage"
        stage.mkdir(mode=0o700)
        private = stage / "private"
        private.mkdir(mode=0o700)
        (stage / "connector").mkdir(mode=0o700)
        binary = private / "nomad"
        install_binary(binary)
        run([binary, "tls", "ca", "create"], cwd=private)
        for role in ("server", "cli"):
            run([binary, "tls", "cert", "create", "-" + role, "-region=global"], cwd=private)
        key = run([binary, "operator", "gossip", "keyring", "generate"])
        if not re.fullmatch(r"[A-Za-z0-9_+/=-]{43,44}", key):
            raise RuntimeError("Unexpected gossip key format")
        config = (PROJECT / "agent.hcl.in").read_text().replace("@GOSSIP_KEY@", key)
        (private / "agent.hcl").write_text(config)
        (private / "management.token").write_text(str(uuid4()) + "\n")
        (private / "bootstrap.pending").touch()
        record = {"format": 1, "uid": uid, "version": VERSION, "token_name": "catalog-" + str(uuid4()),
                  "nomad": sha256(binary), "agent.hcl": sha256(private / "agent.hcl")}
        (private / "install.json").write_text(json.dumps(record))
        stage.chmod(0o711)
        # The bootstrap identity must reach disk before a server can commit it in Raft.
        for path in private.iterdir():
            sync_path(path)
        for path in (private, stage / "connector", stage):
            sync_path(path)
        # Linux RENAME_NOREPLACE also protects an empty directory created during download.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(-100, os.fsencode(stage), -100, os.fsencode(ROOT), 1) != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), ROOT)
        sync_path(ROOT.parent)
    return record


def bootstrap(api, pending, token):
    api.token = token
    try:
        identity = api.call("GET", "/v1/acl/token/self")
    except ApiError as exc:
        if not pending or exc.status not in (400, 403, 404):
            raise
        if os.path.lexists(PRIVATE / "data/server/acl-bootstrap-reset"):
            raise RuntimeError("A manual ACL bootstrap reset is pending. Inspect the cluster")
        api.token = None
        identity = api.call("POST", "/v1/acl/bootstrap", {"BootstrapSecret": token})
        api.token = token
    if identity is None or identity.get("Type") != "management" or identity.get("SecretID") != token:
        raise RuntimeError("Stored credential did not identify the managed cluster administrator")


def scoped_token(api, name, pending):
    # A named token can be recovered if Nomad committed a create but the reply was lost.
    tokens = [t for t in api.call("GET", "/v1/acl/tokens") if t["Name"] == name]
    if len(tokens) == 1:
        token = api.call("GET", "/v1/acl/token/" + str(UUID(tokens[0]["AccessorID"])))
    elif not tokens and pending:
        token = api.call("POST", "/v1/acl/token", {"Name": name, "Type": "client", "Policies": [POLICY]})
    else:
        raise RuntimeError("Expected one managed connector token. Inspect ACL state")
    if (token.get("Type") != "client" or token.get("Policies") != [POLICY] or token.get("Roles")
            or token.get("Global") or token.get("Name") != name):
        raise RuntimeError("Connector token scope differs from the installation record")
    return str(UUID(token["SecretID"]))


def publish_credentials(uid, token):
    # Root keeps canonical originals. Never read user-owned files in a root TLS context.
    data = {name: (PRIVATE / name).read_bytes() for name in CLIENT_FILES}
    data["token"] = (token + "\n").encode()
    for name, value in data.items():
        with tempfile.NamedTemporaryFile(dir=CONNECTOR, delete=False) as dest:
            try:
                dest.write(value)
                dest.flush()
                os.fchmod(dest.fileno(), 0o400)
                os.fchown(dest.fileno(), uid, -1)
                os.fsync(dest.fileno())
                os.replace(dest.name, CONNECTOR / name)
            finally:
                Path(dest.name).unlink(missing_ok=True)
    CONNECTOR.chmod(0o711)
    sync_path(CONNECTOR)


def require_forbidden(api, path):
    try:
        api.call("GET", path)
    except ApiError as exc:
        if exc.status == 403:
            return
        raise
    raise RuntimeError(f"Unexpected ACL access to {path}. Inspect the cluster's policies")


def provision_resource(api, path, definition, pending):
    try:
        resource = api.call("GET", path)
    except ApiError as exc:
        if exc.status != 404 or not pending:
            raise
        api.call("POST", path, definition)
        resource = api.call("GET", path)
    if not isinstance(resource, dict):
        raise TypeError(f"Nomad returned an invalid resource for {path}")
    return resource


def provision(record):
    pending_file = PRIVATE / "bootstrap.pending"
    pending = pending_file.exists()
    api = Api(PRIVATE)
    until(lambda: api.call("GET", "/v1/status/leader") == PEER, 90, "the local Raft leader")
    bootstrap(api, pending, secret_file(PRIVATE / "management.token"))
    namespace = provision_resource(api, "/v1/namespace/" + NAMESPACE,
                                   {"Name": NAMESPACE, "Capabilities": {"EnabledTaskDrivers": ["docker"]}}, pending)
    if (namespace.get("Capabilities") or {}).get("EnabledTaskDrivers") != ["docker"]:
        raise RuntimeError("Project namespace driver restrictions differ from the installed scope")
    policy = provision_resource(api, "/v1/acl/policy/" + POLICY, {"Name": POLICY, "Rules": RULES}, pending)
    if policy.get("Rules") != RULES or policy.get("JobACL"):
        raise RuntimeError("Connector policy differs from the installed scope")
    token = scoped_token(api, record["token_name"], pending)
    api.token = None
    require_forbidden(api, "/v1/nodes")
    api.token = token
    require_forbidden(api, "/v1/acl/tokens")
    result = until(lambda: ready(api), 90, "one ready, eligible Docker client")
    publish_credentials(record["uid"], token)
    pending_file.unlink(missing_ok=True)
    sync_path(PRIVATE)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=["check", "install"])
    parser.add_argument("--operator", required=True, help="existing local account for the batch connector")
    args = parser.parse_args()
    uid = pwd.getpwnam(args.operator).pw_uid
    if uid == 0:
        raise RuntimeError("Choose a non-root account for the batch connector")
    os.umask(0o077)
    # Use a system path for privileged helpers. A lock covers all cluster-side provisioning.
    os.environ["PATH"] = SYSTEM_PATH
    environment = check_host()
    with open("/run/catalog-nomad.install.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = managed_install(uid)
        unit_exists = check_unit(record)
        if args.action == "check":
            print(json.dumps({"check": "passed", "environment": environment}, sort_keys=True))
            return
        if record is None:
            record = prepare(uid)
        run([PRIVATE / "nomad", "config", "validate", PRIVATE / "agent.hcl"])
        if not unit_exists:
            # Publish the complete unit without overwriting a destination that appeared meanwhile.
            with tempfile.NamedTemporaryFile(dir=UNIT.parent) as tmp:
                tmp.write((PROJECT / UNIT.name).read_bytes())
                tmp.flush()
                os.fchmod(tmp.fileno(), 0o644)
                os.link(tmp.name, UNIT)
        run(["systemctl", "--no-ask-password", "daemon-reload"])
        check_unit(record)
        run(["systemctl", "--no-ask-password", "enable", "--now", UNIT.name])
        print(json.dumps({**provision(record), "environment": environment}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        # Validation and key-generation output may include sensitive values.
        sys.exit(f"{Path(err.cmd[0]).name} failed (exit {err.returncode}) during {err.cmd[1]}")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, http.client.HTTPException, subprocess.TimeoutExpired) as err:
        sys.exit(str(err))
