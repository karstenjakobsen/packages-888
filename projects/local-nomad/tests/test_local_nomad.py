"""Offline tests. No root, daemon, Docker socket, listening port or release download."""
import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT.parents[1] / "connectors/local-nomad"))
import batch
import install
import nomad_api
import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enter_temp())
        self.archive = self.dir / release.ARCHIVE
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr("nomad", b"sample binary")
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.dir / release.SUMS).write_text(f"{self.digest}  {release.ARCHIVE}\n")

    def enter_temp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return temp.name

    def verify(self, key=release.FINGERPRINT):
        proc = Mock(stdout=f"[GNUPG:] VALIDSIG subkey date 0 0 4 0 1 8 00 {key}\n")
        with patch.object(release, "DIGEST", self.digest), patch.object(subprocess, "run", return_value=proc) as run:
            release.verify(self.dir)
            self.assertEqual(run.call_args.args[0][-3:], ["--verify", release.SIGNATURE, release.SUMS])
            self.assertTrue(run.call_args.kwargs["check"])

    def test_valid_and_corrupt_archive(self):
        self.verify()
        self.archive.write_bytes(self.archive.read_bytes() + b"tamper")
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.verify()

    def test_wrong_signer_and_ambiguous_or_wrong_filename(self):
        with self.assertRaisesRegex(RuntimeError, "signature"):
            self.verify(key="0" * 40)
        for lines in ([release.ARCHIVE] * 2, ["other.zip"]):
            (self.dir / release.SUMS).write_text("".join(f"{self.digest}  {name}\n" for name in lines))
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                self.verify()

    def test_bad_signature_never_publishes_binary(self):
        target = self.dir / "nomad"
        with (patch.object(release, "download"),
              patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(2, ["gpg", "--verify"])),
              self.assertRaises(subprocess.CalledProcessError)):
            release.install_binary(target)
        self.assertFalse(target.exists())


class CredentialsTests(unittest.TestCase):
    def test_provision_after_interruption_preserves_acl_identity_and_workloads(self):
        with tempfile.TemporaryDirectory() as root:
            private, connector = Path(root) / "private", Path(root) / "connector"
            private.mkdir()
            connector.mkdir()
            admin, client, accessor = (str(uuid4()) for _ in range(3))
            admin_file = private / "management.token"
            admin_file.write_text(admin)
            admin_file.chmod(0o600)
            for name in install.CLIENT_FILES:
                (private / name).write_text("test TLS material")
            pending = private / "bootstrap.pending"
            pending.touch()
            record = {"token_name": "catalog-fixture", "uid": os.getuid()}
            existing = {"Name": record["token_name"], "AccessorID": accessor, "Type": "client",
                        "Policies": [install.POLICY], "SecretID": client}
            api = Mock()
            reads = {
                "/v1/status/leader": install.PEER, "/v1/acl/token/self": {"Type": "management", "SecretID": admin},
                "/v1/namespace/" + install.NAMESPACE: {"Capabilities": {"EnabledTaskDrivers": ["docker"]}},
                "/v1/acl/policy/" + install.POLICY: {"Rules": install.RULES},
                "/v1/acl/tokens": [existing], "/v1/acl/token/" + accessor: existing,
            }

            def request(method, path, *args, **kwargs):
                self.assertEqual(method, "GET", "Rerun mutated Nomad")
                if api.token != admin and path != "/v1/status/leader":
                    raise nomad_api.ApiError(403, method, path)
                return reads[path]  # Unexpected operations, including job traffic, fail the test.

            api.call.side_effect = request
            with (patch.object(install, "PRIVATE", private), patch.object(install, "CONNECTOR", connector),
                  patch.object(install, "Api", return_value=api), patch.object(install, "ready", return_value=True)):
                # Nomad has committed the ACLs but the first connector publication was interrupted.
                with patch.object(install, "publish_credentials", side_effect=OSError("interrupted")), \
                        self.assertRaises(OSError):
                    install.provision(record)
                self.assertTrue(pending.exists())
                install.provision(record)
                self.assertFalse(pending.exists())
                copies = {p.name: p.read_bytes() for p in connector.iterdir()}
                install.provision(record)
                self.assertEqual(copies, {p.name: p.read_bytes() for p in connector.iterdir()})
                self.assertEqual(admin_file.read_text(), admin)
                self.assertEqual(nomad_api.secret_file(connector / "token"), client)

    def test_malformed_acl_resource_is_reported_without_a_write(self):
        api = Mock()
        api.call.return_value = None
        path = "/v1/acl/policy/" + install.POLICY
        with self.assertRaisesRegex(TypeError, "invalid resource"):
            install.provision_resource(api, path, {}, True)
        api.call.assert_called_once_with("GET", path)

    def test_interrupted_acl_resource_write_reconciles_without_overwrite(self):
        api = Mock()
        existing = {"Name": install.POLICY, "Rules": install.RULES}
        path = "/v1/acl/policy/" + install.POLICY
        api.call.side_effect = [nomad_api.ApiError(404, "GET", path), ConnectionError(), existing, existing]
        with self.assertRaises(ConnectionError):
            install.provision_resource(api, path, existing, True)
        for pending in (True, False):
            self.assertEqual(install.provision_resource(api, path, existing, pending), existing)
        self.assertEqual([call.args[0] for call in api.call.call_args_list], ["GET", "POST", "GET", "GET"])

    def test_live_acl_probe_rejects_success_or_an_unrelated_failure(self):
        api = Mock()
        with self.assertRaisesRegex(RuntimeError, "Unexpected ACL access"):
            install.require_forbidden(api, "/v1/acl/tokens")
        api.call.side_effect = nomad_api.ApiError(500, "GET", "/v1/acl/tokens")
        with self.assertRaises(nomad_api.ApiError):
            install.require_forbidden(api, "/v1/acl/tokens")
        api.call.side_effect = nomad_api.ApiError(403, "GET", "/v1/acl/tokens")
        install.require_forbidden(api, "/v1/acl/tokens")

    def test_lost_bootstrap_reply_reconciles_from_persisted_secret(self):
        token = str(uuid4())
        api = Mock()
        identity = {"Type": "management", "SecretID": token}
        api.call.side_effect = [nomad_api.ApiError(403, "GET", "/self"), ConnectionError(), identity]
        with self.assertRaises(ConnectionError):
            install.bootstrap(api, True, token)
        install.bootstrap(api, True, token)
        self.assertEqual([x.args[0] for x in api.call.call_args_list], ["GET", "POST", "GET"])
        self.assertEqual(api.call.call_args_list[1].args[2], {"BootstrapSecret": token})

    def test_completed_install_never_rebootstraps_invalid_credential(self):
        api = Mock()
        api.call.side_effect = nomad_api.ApiError(403, "GET", "/self")
        with self.assertRaises(nomad_api.ApiError):
            install.bootstrap(api, False, str(uuid4()))
        self.assertEqual(api.call.call_count, 1)

    def test_resume_token_creation_including_lost_reply(self):
        name = "install-token"
        t = {"Name": name, "AccessorID": str(uuid4()), "SecretID": str(uuid4()),
             "Type": "client", "Policies": [install.POLICY], "Global": False}
        api = Mock()
        api.call.side_effect = [[], ConnectionError(), [t], t, [t], t]
        with self.assertRaises(ConnectionError):
            install.scoped_token(api, name, True)
        self.assertEqual(install.scoped_token(api, name, True), t["SecretID"])
        self.assertEqual(install.scoped_token(api, name, False), t["SecretID"])
        self.assertEqual(sum(c.args[0] == "POST" for c in api.call.call_args_list), 1)

    def test_widened_missing_or_ambiguous_tokens_fail_closed(self):
        named = {"Name": "t", "AccessorID": str(uuid4())}
        for responses in ([[]], [[named, named]], [[named], dict(named, Type="management")],
                          [[named], dict(named, Type="client", Policies=[install.POLICY], Roles=["admin"])]):
            api = Mock()
            api.call.side_effect = responses
            with self.assertRaises(RuntimeError):
                install.scoped_token(api, "t", False)
            self.assertTrue(all(c.args[0] == "GET" for c in api.call.call_args_list))

    def test_secret_publication_is_private_and_does_not_follow_destination_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private, dest = root / "private", root / "connector"
            private.mkdir()
            dest.mkdir()
            for name in install.CLIENT_FILES:
                (private / name).write_text("fixture")
            sentinel = root / "unrelated"
            sentinel.write_text("preserve")
            (dest / "token").symlink_to(sentinel)
            token = str(uuid4())
            with patch.object(install, "PRIVATE", private), patch.object(install, "CONNECTOR", dest):
                install.publish_credentials(os.getuid(), token)
            self.assertEqual(nomad_api.secret_file(dest / "token"), token)
            self.assertEqual(sentinel.read_text(), "preserve")
            self.assertFalse((dest / "management.token").exists())
            for path in dest.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)


class OwnershipTests(unittest.TestCase):
    def test_fresh_unit_with_empty_systemd_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            props = {"LoadState": "not-found", "ActiveState": "inactive"}
            with (patch.object(install, "UNIT", Path(tmp) / install.UNIT.name),
                  patch.object(install, "unit_properties", return_value=props),
                  patch.object(install, "check_ports"), patch.object(install, "check_other_agents")):
                self.assertFalse(install.check_unit(None))

    def test_detect_running_agent_with_custom_unit_and_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            pid = proc / "123"
            pid.mkdir()
            (pid / "comm").write_text("nomad\n")
            (pid / "cmdline").write_bytes(b"/opt/custom/nomad\0agent\0-config=/custom/agent.hcl\0")
            with self.assertRaisesRegex(RuntimeError, "Unmanaged Nomad agent"):
                install.check_other_agents("0", proc)
            install.check_other_agents("123", proc)
            (pid / "cmdline").write_bytes(b"nomad\0version\0")
            install.check_other_agents("0", proc)

    def test_unmanaged_root_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "existing"
            sentinel.write_text("existing")
            with patch.object(install, "ROOT", root), self.assertRaises(RuntimeError):
                install.managed_install(1000)
            self.assertEqual(sentinel.read_text(), "existing")

    def test_refuse_foreign_unit_dropin_or_occupied_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit = Path(tmp) / install.UNIT.name
            unit.write_text("other service")
            props = {"LoadState": "loaded", "ActiveState": "inactive", "FragmentPath": str(unit)}
            with patch.object(install, "UNIT", unit), patch.object(install, "unit_properties", return_value=props):
                with self.assertRaisesRegex(RuntimeError, "replace"):
                    install.check_unit(None)
                unit.write_bytes((PROJECT / unit.name).read_bytes())
                props["DropInPaths"] = "/etc/override.conf"
                with self.assertRaisesRegex(RuntimeError, "override"):
                    install.check_unit({"format": 1})
                props.pop("DropInPaths")
                unit.chmod(0o664)
                with self.assertRaisesRegex(RuntimeError, "replace"):
                    install.check_unit({"format": 1})
                unit.chmod(0o644)
                with (patch.object(install.os, "geteuid", return_value=unit.stat().st_uid + 1),
                      self.assertRaisesRegex(RuntimeError, "replace")):
                    install.check_unit({"format": 1})
                with patch.object(install.socket, "socket") as sock:
                    sock.return_value.__enter__.return_value.bind.side_effect = OSError("busy")
                    with self.assertRaisesRegex(RuntimeError, "4646"):
                        install.check_unit({"format": 1})

    def test_owned_active_unit_does_not_probe_its_own_ports(self):
        unit = PROJECT / install.UNIT.name
        props = {"LoadState": "loaded", "ActiveState": "active", "FragmentPath": str(unit)}
        with patch.object(install, "UNIT", unit), patch.object(install, "unit_properties", return_value=props), \
                patch.object(install, "check_ports") as probe, patch.object(install, "check_other_agents"):
            self.assertTrue(install.check_unit({"format": 1}))
            probe.assert_not_called()


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.batch = batch.Batch(self.api)
        self.source = (PROJECT / "examples/squares.py").read_bytes()
        self.job = batch.job_spec("squares", self.source)
        self.alloc = str(uuid4())
        self.metadata = {"ID": self.job["ID"], "Meta": batch.META, "Status": "dead"}

    def test_job_payload_runs_the_example_inside_the_interpreter(self):
        group, = self.job["TaskGroups"]
        task, = group["Tasks"]
        config = task["Config"]
        self.assertEqual(self.job["Namespace"], nomad_api.NAMESPACE)
        self.assertEqual(self.job["Type"], "batch")
        self.assertEqual(task["Driver"], "docker")
        self.assertEqual(task["User"], "65534:65534")
        self.assertEqual(config["network_mode"], "none")
        self.assertEqual(config["cap_drop"], ["ALL"])
        self.assertEqual(config["security_opt"], ["no-new-privileges"])
        self.assertTrue(config["readonly_rootfs"])
        self.assertFalse(config["privileged"])
        self.assertNotIn("volumes", config)
        self.assertIn("@sha256:", config["image"])
        self.assertEqual(group["RestartPolicy"]["Attempts"], 0)
        template, = task["Templates"]
        self.assertEqual(template["DestPath"], "local/project.b64")
        with tempfile.TemporaryDirectory() as task_dir:
            (Path(task_dir) / "project.b64").write_text(template["EmbeddedTmpl"])
            output = subprocess.check_output([sys.executable, *config["args"]], text=True,
                                             env={**os.environ, "NOMAD_TASK_DIR": task_dir})
        self.assertEqual(output, "sum-of-squares=338350\n")

    def test_source_bytes_cannot_set_host_features_or_template_directives(self):
        # Even jobspec-shaped input changes only the literal program file.
        source = b'{"Driver":"raw_exec","privileged":true,"network_mode":"host","volumes":["/:/host"]}\n{{example}}'
        self.api.call.side_effect = [{"JobModifyIndex": 0}, {"EvalID": "evaluation"}]
        self.batch.submit("squares", source)
        submitted = self.api.call.call_args.args[2]["Job"]
        template, = submitted["TaskGroups"][0]["Tasks"][0]["Templates"]
        self.assertEqual(base64.b64decode(template["EmbeddedTmpl"], validate=True), source)
        template["EmbeddedTmpl"] = base64.b64encode(self.source).decode()
        self.assertEqual(submitted, self.job)

    def test_reject_path_injection_and_oversized_source(self):
        for name in ("../job", "x?purge=true", "/v1/jobs", "x\ny"):
            with self.assertRaises(ValueError):
                self.batch.status(name)
        self.api.call.assert_not_called()
        with self.assertRaises(ValueError):
            batch.job_spec("squares", b"a" * 49153)

    def test_plan_and_submit_create_only(self):
        self.api.call.side_effect = [{"JobModifyIndex": 0}, {"EvalID": "evaluation"}]
        self.assertEqual(self.batch.submit("squares", self.source)["evaluation"], "evaluation")
        plan, submit = self.api.call.call_args_list
        self.assertEqual(plan.args, ("POST", "/v1/job/project-squares/plan", {"Job": self.job}))
        self.assertEqual(submit.args, ("POST", "/v1/jobs", {"Job": self.job, "EnforceIndex": True, "JobModifyIndex": 0}))
        for call in (plan, submit):
            self.assertEqual(call.kwargs["query"], {"namespace": nomad_api.NAMESPACE})

    def test_no_submission_after_placement_failure_or_existing_job(self):
        for answer in ({"JobModifyIndex": 0, "FailedTGAllocs": {"batch": {}}}, {"JobModifyIndex": 9}):
            self.api.call.reset_mock()
            self.api.call.return_value = answer
            with self.assertRaises(RuntimeError):
                self.batch.submit("squares", self.source)
            self.assertEqual(self.api.call.call_count, 1)

    def test_logs_use_latest_allocation_and_scoped_nonfollowing_plain_stream(self):
        allocs = [{"CreateIndex": 2, "ID": self.alloc, "ClientStatus": "complete"},
                  {"CreateIndex": 1, "ID": str(uuid4()), "ClientStatus": "failed"}]
        self.api.call.side_effect = [self.metadata, allocs, "calculated output\n"]
        self.assertEqual(self.batch.logs("squares", "stdout"), "calculated output\n")
        call = self.api.call.call_args
        self.assertEqual(call.args[1], "/v1/client/fs/logs/" + self.alloc)
        self.assertEqual(call.kwargs, {"query": {"namespace": nomad_api.NAMESPACE, "type": "stdout",
                         "task": "python", "follow": "false", "plain": "true"}, "plain": True})

    def test_cleanup_is_scoped_repeatable_and_checks_ownership(self):
        self.api.call.side_effect = [self.metadata, [], {}, nomad_api.ApiError(404, "GET", "/job"),
                                     dict(self.metadata, Meta={})]
        self.assertEqual(self.batch.cleanup("squares")["state"], "purge requested")
        call = self.api.call.call_args
        self.assertEqual(call.args[:2], ("DELETE", "/v1/job/project-squares"))
        self.assertEqual(call.kwargs["query"], {"namespace": nomad_api.NAMESPACE, "purge": "true"})
        self.assertEqual(self.batch.cleanup("squares")["state"], "absent")
        with self.assertRaisesRegex(RuntimeError, "outside"):
            self.batch.cleanup("squares")
        self.assertEqual(self.api.call.call_count, 5)

    def test_failed_batch_is_not_success(self):
        self.api.call.side_effect = [self.metadata, [{"ID": self.alloc, "ClientStatus": "failed", "CreateIndex": 1}]]
        with self.assertRaisesRegex(RuntimeError, "without a completed allocation"):
            self.batch.completed("squares")

    def test_wait_requires_terminal_job_and_successful_task_exit(self):
        alloc = {"ID": self.alloc, "ClientStatus": "complete", "CreateIndex": 1}
        good = {"State": "dead", "Failed": False, "Events": [
            {"Type": "Started"}, {"Type": "Terminated", "Details": {"exit_code": "0", "signal": "0"}}]}
        for changes in ({"Failed": True}, {"State": "running"}, {"Events": []},
                        {"Events": [{"Type": "Terminated", "ExitCode": 0, "Signal": 9}]},
                        {"Events": [{"Type": "Terminated", "Details": {"exit_code": "1"}, "ExitCode": 0}]}):
            self.api.call.side_effect = [self.metadata, [alloc], {"TaskStates": {"python": dict(good, **changes)}}]
            with self.assertRaisesRegex(RuntimeError, "successful python task exit"):
                self.batch.completed("squares")
        for job_state in ("running", "dead"):
            self.api.call.side_effect = [dict(self.metadata, Status=job_state), [alloc], {"TaskStates": {"python": good}}]
            result = self.batch.completed("squares")
            if job_state == "running":
                self.assertIsNone(result)
            else:
                self.assertEqual((result["exit_code"], result["allocation"]), (0, self.alloc))

    def test_connector_refuses_management_token_before_job_api(self):
        self.api.call.return_value = {"Type": "management", "SecretID": str(uuid4())}
        with patch.object(batch, "Api", return_value=self.api), patch.object(batch, "secret_file"), \
                patch.object(batch.os, "geteuid", return_value=1000), \
                self.assertRaisesRegex(RuntimeError, "scoped client"):
            batch.main(["cleanup", "squares"])
        self.api.call.assert_called_once_with("GET", "/v1/acl/token/self")

    def test_malformed_acl_identity_stops_before_job_operations(self):
        self.api.call.return_value = None
        with (patch.object(batch, "Api", return_value=self.api), patch.object(batch, "secret_file"),
              patch.object(batch.os, "geteuid", return_value=1000), self.assertRaisesRegex(RuntimeError, "scoped client")):
            batch.main(["cleanup", "squares"])
        self.api.call.assert_called_once_with("GET", "/v1/acl/token/self")

    def test_root_cannot_run_normal_job_operations(self):
        with (patch.object(batch.os, "geteuid", return_value=0), patch.object(batch, "secret_file") as read,
              self.assertRaisesRegex(RuntimeError, "non-root")):
            batch.main(["submit", "squares", "-"])
        read.assert_not_called()

    def test_typed_submit_accepts_source_from_stdin(self):
        self.api.call.side_effect = [{"Type": "client", "Policies": [install.POLICY]},
                                     {"JobModifyIndex": 0}, {"EvalID": "evaluation"}]
        with (patch.object(batch.os, "geteuid", return_value=1000), patch.object(batch, "secret_file"),
              patch.object(batch, "Api", return_value=self.api),
              patch.object(sys, "stdin", Mock(buffer=io.BytesIO(self.source))),
              patch.object(batch, "kernel_info", return_value={"platform": "wsl2", "hostname": "fixture"}),
              contextlib.redirect_stdout(io.StringIO()) as stdout):
            batch.main(["submit", "squares", "-"])
        self.assertEqual(json.loads(stdout.getvalue()), {"platform": "wsl2", "hostname": "fixture", "evaluation": "evaluation",
                                                       "job": "project-squares"})
        self.assertEqual(self.api.call.call_args.args[2]["Job"], self.job)

    def test_readiness_requires_the_topology_and_healthy_driver(self):
        node = {"ID": self.alloc, "Status": "ready", "SchedulingEligibility": "eligible",
                "Drivers": {"docker": {"Detected": True, "Healthy": True}}}
        for change in ({}, {"Status": "down"}, {"SchedulingEligibility": "ineligible"}, {"Drivers": {}}):
            self.api.call.side_effect = [nomad_api.PEER, [nomad_api.PEER], [node], dict(node, **change)]
            self.assertEqual(bool(nomad_api.ready(self.api)), not change)
        self.api.call.side_effect = [nomad_api.PEER, [nomad_api.PEER, "other"]]
        self.assertIsNone(nomad_api.ready(self.api))

    def test_transport_never_follows_redirect_or_discloses_body(self):
        api = nomad_api.Api.__new__(nomad_api.Api)
        api.token, api.context = str(uuid4()), Mock()
        for status in (301, 302, 303, 307, 308, 403):
            response = Mock(status=status)
            response.getheader.return_value = "https://elsewhere.invalid/receive"
            response.read.return_value = api.token.encode()
            with patch.object(nomad_api.http.client, "HTTPSConnection") as make:
                context = MagicMock()
                context.__enter__.return_value = response
                make.return_value.getresponse.return_value = context
                with self.assertRaises(nomad_api.ApiError) as error:
                    api.call("POST", "/v1/jobs", {"Job": self.job}, query={"namespace": nomad_api.NAMESPACE})
                make.assert_called_once_with("127.0.0.1", 4646, timeout=8, context=api.context)
                make.return_value.request.assert_called_once()
                response.getheader.assert_not_called()
                args = make.return_value.request.call_args.args
                self.assertEqual(args[1], "/v1/jobs?namespace=catalog-projects")
                self.assertEqual(json.loads(args[2]), {"Job": self.job})
                self.assertEqual(args[3]["X-Nomad-Token"], api.token)
                self.assertNotIn(api.token, str(error.exception))
                response.read.assert_not_called()
                context.__exit__.assert_called_once()


class WorkerContractTests(unittest.TestCase):
    def test_reviewed_files_are_sufficient_for_isolated_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "snapshot"
            for package, files in [
                ("projects/local-nomad", ["install.py", "release.py", "agent.hcl.in", "catalog-nomad.service"]),
                ("connectors/local-nomad", ["nomad_api.py", "host_environment.py", "batch.py"]),
            ]:
                (catalog / package).mkdir(parents=True)
                for name in files:
                    shutil.copy2(PROJECT.parents[1] / package / name, catalog / package / name)
            for entrypoint in ("projects/local-nomad/install.py", "connectors/local-nomad/batch.py"):
                ret = subprocess.run(["/usr/bin/python3", "-ISB", catalog / entrypoint, "--help"], cwd="/",
                                     stdin=subprocess.DEVNULL, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
                                     check=True, text=True, capture_output=True)
                self.assertIn("usage:", ret.stdout)

    def test_smoke_checks_wait_and_stdout_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects/local-nomad"
            project.mkdir(parents=True)
            shutil.copy2(PROJECT / "smoke.sh", project)
            stub = root / "connectors/local-nomad/batch.py"
            stub.parent.mkdir(parents=True)
            stub.write_text("""#!/bin/sh
echo "$1" >> "$OPS"
case "$1" in
    wait) exit "$WAIT_CODE" ;;
    logs) echo "$MARKER" ;;
esac
""")
            stub.chmod(0o755)
            ops = root / "ops"
            for wait_code, marker, success in [(1, "sum-of-squares=338350", False), (0, "wrong", False),
                                               (0, "sum-of-squares=338350", True)]:
                ops.write_text("")
                result = subprocess.run([project / "smoke.sh"], check=False, capture_output=True,
                                        env={**os.environ, "OPS": str(ops), "MARKER": marker, "WAIT_CODE": str(wait_code)})
                self.assertEqual(result.returncode == 0, success)
                calls = ops.read_text().splitlines()
                self.assertIn("wait", calls)
                self.assertEqual("logs" in calls, wait_code == 0)
                self.assertEqual("cleanup" in calls, success)


if __name__ == "__main__":
    unittest.main()
