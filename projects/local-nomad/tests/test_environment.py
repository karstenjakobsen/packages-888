"""Offline fixtures for the views seen by the root worker, operator and sandbox."""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT.parents[1] / "connectors/local-nomad"))
import batch
import host_environment as host
import install


class EnvironmentTests(unittest.TestCase):
    def test_linux_kernel_classification_from_both_proc_files_without_environment(self):
        fixtures = [
            ("6.6.87.2-MiCrOsOfT-StAnDaRd-WSL2", "", False, "wsl2"),
            ("4.4.0-microsoft-standard", "", False, "wsl2"),
            ("custom", "Linux version 6.1-custom-wSl2", False, "wsl2"),
            ("4.4.0-19041-Microsoft", "", False, "wsl1"),
            ("3.4.0-Microsoft", "", False, "wsl1"),
            ("4.4.0", "Linux version 4.4.0 (Microsoft@Microsoft.com)", False, "wsl1"),
            ("custom", "Linux version custom-WSL1", False, "wsl1"),
            ("5.15-Microsoft", "", False, "wsl"),
            ("custom-WSL1", "Linux version custom-WSL2", False, "wsl"),
            ("custom", "", True, "wsl"),
            ("6.8.0-azure", "Linux version 6.8.0-azure", False, "native-linux"),
            ("", "", False, "unknown"),
        ]
        for release, version, metadata, expected in fixtures:
            proc = {Path("/proc/sys/kernel/osrelease"): release, Path("/proc/version"): version}
            with (self.subTest(release=release, version=version, metadata=metadata),
                  patch.dict(os.environ, {}, clear=True),
                  patch.object(host.platform, "system", return_value="Linux"),
                  patch.object(host.platform, "release", return_value=""),
                  patch.object(host, "read_text", side_effect=proc.__getitem__),
                  patch.object(host.os.path, "isdir", return_value=metadata),
                  patch.object(host.os.path, "isfile", return_value=False)):
                self.assertEqual(host.kernel_info()["platform"], expected)

    def test_unsupported_platform_skips_linux_probes(self):
        with (patch.object(host.platform, "system", return_value="Darwin"),
              patch.object(host, "systemd_info") as systemd, patch.object(host, "docker_info") as docker,
              patch.object(host, "cgroup_info") as cgroups):
            result = host.detect_environment()
            self.assertEqual(result["platform"], "unsupported")
            for key, probe in (("systemd", systemd), ("cgroups", cgroups), ("docker", docker)):
                self.assertIsNone(result[key])
                probe.assert_not_called()

    def test_system_manager_confirms_missing_unit_or_reports_inability_to_inspect(self):
        for rc, output, error, manager, unit in [
            (4, "LoadState=not-found\nActiveState=inactive", "", "reachable", "not-found"),
            (0, "LoadState=loaded\nActiveState=active", "", "reachable", "loaded"),
            (1, "", "Failed to connect to bus: Permission denied", "permission-denied", None),
            (1, "", "System has not been booted with systemd", "unreachable", None),
        ]:
            response = subprocess.CompletedProcess([], rc, output, error)
            with (self.subTest(manager=manager, unit=unit),
                  patch.object(host, "read_text", return_value="systemd"),
                  patch.object(host.subprocess, "run", return_value=response) as run):
                result = host.systemd_info()
                self.assertEqual((result["manager"], result["docker_unit_load"]), (manager, unit))
                self.assertEqual(result["ready"], manager == "reachable")
                self.assertEqual(run.call_args.args[0][:5], ["/usr/bin/systemctl", "--system", "show", "--all", "docker.service"])
        with (patch.object(host, "read_text", return_value="init"),
              patch.object(host, "unit_properties", return_value={"LoadState": "loaded"})):
            self.assertFalse(host.systemd_info()["ready"])

    def test_v2_mount_and_required_controllers(self):
        for contents, error, state, missing in [
            ("cpu cpuset io memory pids hugetlb", None, "v2", []),
            ("cpu cpuset", None, "v2", ["io", "memory", "pids"]),
            ("", FileNotFoundError(), "v2-unavailable", None),
            ("", PermissionError(), "unreadable", None),
        ]:
            with self.subTest(state=state, missing=missing), patch.object(Path, "read_text", return_value=contents, side_effect=error):
                result = host.cgroup_info()
                self.assertEqual((result["state"], result["missing"], result["ready"]), (state, missing, missing == []))

    def test_runtime_identity_comes_from_info_over_fixed_socket(self):
        for os_name, runtime, rootless in [
            ("Docker Desktop", "docker-desktop", False), ("Ubuntu 24.04", "linux-engine", False),
            ("Ubuntu 24.04", "linux-engine", True), (None, "unknown", False),
        ]:
            info = {"OperatingSystem": os_name, "OSType": "linux", "SecurityOptions": ["name=rootless"] if rootless else [],
                    "CgroupVersion": "2", "Runtimes": {"runc": {}}, "Labels": ["private arbitrary daemon metadata"]}
            body = json.dumps(info).encode()
            with (self.subTest(os_name=os_name, rootless=rootless), patch.object(Path, "stat", return_value=Mock(st_mode=stat.S_IFSOCK)),
                  patch.object(host.socket, "socket") as new_socket):
                sock = new_socket.return_value.__enter__.return_value
                sock.makefile.return_value = io.BytesIO(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + body)
                result = host.docker_info()
                new_socket.assert_called_once_with(host.socket.AF_UNIX, host.socket.SOCK_STREAM)
                sock.connect.assert_called_once_with("/var/run/docker.sock")
                self.assertIn(b"GET /info HTTP/1.1", sock.sendall.call_args.args[0])
                self.assertEqual((result["socket"], result["daemon"], result["runtime"]), ("present", "reachable", runtime))
                self.assertEqual((result["rootless"], result["runc"], result["cgroup_version"]), (rootless, True, "2"))
                self.assertNotIn("private arbitrary", json.dumps(result))

    def test_socket_absence_permissions_and_daemon_failures(self):
        for mode, stat_error, engine_error, socket_state, daemon in [
            (None, FileNotFoundError(), None, "missing", "unreachable"),
            (None, PermissionError(), None, "unknown", "permission-denied"),
            (stat.S_IFREG, None, None, "not-a-socket", "unreachable"),
            (stat.S_IFSOCK, None, PermissionError(), "present", "permission-denied"),
            (stat.S_IFSOCK, None, ConnectionRefusedError(), "present", "unreachable"),
            (stat.S_IFSOCK, None, ValueError(), "present", "invalid-response"),
        ]:
            with (self.subTest(socket_state=socket_state, daemon=daemon),
                  patch.object(Path, "stat", return_value=Mock(st_mode=mode), side_effect=stat_error),
                  patch.object(host, "engine_info", side_effect=engine_error) as engine):
                result = host.docker_info()
                self.assertEqual((result["socket"], result["daemon"], result["runtime"]), (socket_state, daemon, "unknown"))
                self.assertEqual(engine.called, socket_state == "present")


class WorkerEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "platform": "wsl2", "architecture": "x86_64",
            "systemd": {"pid1": "systemd", "manager": "reachable", "ready": True, "docker_unit_load": "not-found"},
            "docker": {"endpoint": "unix:///var/run/docker.sock", "socket": "present", "daemon": "reachable",
                       "runtime": "docker-desktop", "cgroup_version": "2", "os_type": "linux", "runc": True, "rootless": False},
            "cgroups": {"state": "v2", "missing": [], "ready": True},
        }

    def test_installer_platform_and_prerequisites(self):
        env = self.environment
        with (patch.object(install.os, "geteuid", return_value=0), patch.object(install, "detect_environment", return_value=env),
              patch.object(install, "unit_properties", return_value={"LoadState": "not-found"}) as unit,
              patch.object(install.shutil, "which", return_value="/usr/bin/gpg"), patch.object(install.os.path, "lexists", return_value=False)):
            for platform, runtime in [("wsl2", "docker-desktop"), ("native-linux", "linux-engine")]:
                with self.subTest(platform=platform), patch.dict(env, platform=platform), patch.dict(env["docker"], runtime=runtime):
                    self.assertEqual(install.check_host(), env)
                    unit.assert_called_with("nomad.service")
            cases = [
                (env, {"platform": "wsl1"}, "wsl --set-version"),
                (env["systemd"], {"ready": False, "pid1": "init"}, "/etc/wsl.conf"),
                (env["cgroups"], {"ready": False, "missing": ["io"]}, "controllers unavailable: io"),
                (env["docker"], {"socket": "missing", "daemon": "unreachable"}, "WSL integration"),
                (env["docker"], {"daemon": "permission-denied"}, "permission-denied"),
                (env["docker"], {"rootless": True}, "rootful"),
                (env["docker"], {"rootless": None}, "rootful"),
                (env["docker"], {"runc": False}, "runc"),
            ]
            for section, changes, message in cases:
                with self.subTest(changes=changes), patch.dict(section, changes), self.assertRaisesRegex(RuntimeError, message):
                    install.check_host()
        with (patch.object(install.os, "geteuid", return_value=1000), patch.object(install, "detect_environment") as probe,
              self.assertRaisesRegex(RuntimeError, "root deployment worker")):
            install.check_host()
        probe.assert_not_called()

    def test_environment_before_enrollment_accepts_either_uid(self):
        for uid in (1000, 0):
            with (self.subTest(uid=uid), patch.object(batch.os, "geteuid", return_value=uid),
                  patch.object(batch, "secret_file") as credential, patch.object(batch, "Api") as nomad,
                  patch.object(batch, "detect_environment", return_value=self.environment),
                  contextlib.redirect_stdout(io.StringIO()) as output):
                batch.main(["environment"])
                self.assertEqual(json.loads(output.getvalue()), self.environment)
                credential.assert_not_called()
                nomad.assert_not_called()

    def test_ready_reports_restricted_view_alongside_cluster_health(self):
        self.environment["docker"].update(daemon="permission-denied", runtime="unknown")
        cluster = {"node": "test-node", "leader": "127.0.0.1:4647", "docker": "healthy"}
        with (patch.object(batch.os, "geteuid", return_value=1000), patch.object(batch, "secret_file"),
              patch.object(batch, "Api") as api, patch.object(batch, "ready", return_value=cluster) as ready,
              patch.object(batch, "detect_environment", return_value=self.environment) as probe,
              contextlib.redirect_stdout(io.StringIO()) as output):
            api.return_value.call.return_value = {"Type": "client", "Policies": [install.POLICY]}
            batch.main(["ready"])
            self.assertEqual(json.loads(output.getvalue()), {**cluster, "environment": self.environment})
            ready.assert_called_once_with(api.return_value)
            probe.assert_called_once_with()
