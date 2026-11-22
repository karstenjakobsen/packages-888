#!/usr/bin/python3 -ISB
"""Run one small Python batch task using the catalog's local Nomad cluster."""
import argparse
import base64
import http.client
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

sys.path.append(str(Path(__file__).resolve().parent))
from host_environment import detect_environment, kernel_info
from nomad_api import NAMESPACE, POLICY, ROOT, Api, ApiError, ready, secret_file, until

IMAGE = "docker.io/library/python@sha256:d76f585fb0d5107dd47143da5e61554fd9cae656a30f3470f815cb8475769b6a"
RUNNER = """import base64, os
from pathlib import Path
source = Path(os.environ["NOMAD_TASK_DIR"], "project.b64").read_bytes()
exec(compile(base64.b64decode(source, validate=True), "project.py", "exec"))
"""
TASK = "python"
META = {"catalog-connector": "local-nomad-v1"}


def job_id(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", value):
        raise ValueError("Use a job name of 1–48 lowercase letters, digits and hyphens starting with a letter")
    return "project-" + value


def job_spec(name, source):
    if not 0 < len(source) <= 48 * 1024:
        raise ValueError("Project source must contain 1–49152 bytes")
    # Only base64 characters reach Nomad's template engine. Executing the file
    # also verifies that the Engine can see the WSL agent's allocation directory.
    task = {
        "Name": TASK, "Driver": "docker", "User": "65534:65534",
        "Resources": {"CPU": 200, "MemoryMB": 96},
        "LogConfig": {"MaxFiles": 2, "MaxFileSizeMB": 1},
        "Templates": [{"DestPath": "local/project.b64", "Perms": "0444", "ChangeMode": "noop",
                       "EmbeddedTmpl": base64.b64encode(source).decode("ascii")}],
        "Config": {
            "image": IMAGE, "runtime": "runc", "command": "python3", "args": ["-I", "-B", "-c", RUNNER],
            "network_mode": "none",
            "readonly_rootfs": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges"],
            "pids_limit": 64, "privileged": False, "cpu_hard_limit": True,
        },
    }
    group = {
        "Name": "batch", "Count": 1, "Tasks": [task],
        "RestartPolicy": {"Attempts": 0, "Mode": "fail"},
        "ReschedulePolicy": {"Attempts": 0, "Unlimited": False},
        "EphemeralDisk": {"SizeMB": 64},
    }
    return {"ID": job_id(name), "Name": job_id(name), "Type": "batch", "Namespace": NAMESPACE,
            "Datacenters": ["dc1"], "Meta": META, "TaskGroups": [group]}


class Batch:
    def __init__(self, api):
        self.api = api

    def request(self, method, path, body=None, *, text_response=False, **params):
        return self.api.call(method, path, body, query={"namespace": NAMESPACE, **params}, plain=text_response)

    def _plan_job(self, job):
        result = self.request("POST", "/v1/job/" + job["ID"] + "/plan", {"Job": job})
        return {"job": job["ID"], "existing_index": result["JobModifyIndex"],
                "placement_failures": result.get("FailedTGAllocs") or {},
                "warnings": result.get("Warnings") or ""}

    def plan(self, name, source):
        return self._plan_job(job_spec(name, source))

    def submit(self, name, source):
        job = job_spec(name, source)
        plan = self._plan_job(job)
        if plan["existing_index"] or plan["placement_failures"]:
            raise RuntimeError("Job already exists or placement failed. Inspect plan and status")
        result = self.request("POST", "/v1/jobs", {"Job": job, "JobModifyIndex": 0, "EnforceIndex": True})
        return {"job": job["ID"], "evaluation": result["EvalID"]}

    def status(self, name):
        path = "/v1/job/" + job_id(name)
        job = self.request("GET", path)
        if (job.get("Meta") or {}).get("catalog-connector") != META["catalog-connector"]:
            raise RuntimeError("This job is outside the connector's managed jobs")
        allocations = self.request("GET", path + "/allocations") or []
        latest = max(allocations, key=lambda a: a["CreateIndex"], default=None)
        return {"job": job["ID"], "status": job["Status"],
                "allocation": str(UUID(latest["ID"])) if latest else None,
                "client_status": latest["ClientStatus"] if latest else None}

    def completed(self, name):
        status = self.status(name)
        if status["client_status"] == "complete":
            alloc = self.request("GET", "/v1/allocation/" + status["allocation"])
            task = (alloc.get("TaskStates") or {}).get(TASK) or {}
            event = next((e for e in reversed(task.get("Events") or []) if e["Type"] == "Terminated"), {})
            details = event.get("Details") or {}
            exit_code = details.get("exit_code", event.get("ExitCode"))
            signal = details.get("signal", event.get("Signal"))
            if (task.get("State") != "dead" or task.get("Failed") is not False
                    or str(exit_code) != "0" or str(signal) != "0"):
                raise RuntimeError(f"Allocation {status['allocation']} lacks a successful {TASK} task exit")
            if status["status"] == "dead":
                return {**status, "exit_code": 0}
            return None  # The scheduler may still be updating the job status.
        if status["client_status"] in ("failed", "lost") or status["status"] == "dead":
            raise RuntimeError(f"Job ended without a completed allocation: {status}")
        return None

    def logs(self, name, stream):
        status = self.status(name)
        if not status["allocation"]:
            raise RuntimeError("Waiting for the first allocation. Check status")
        return self.request("GET", "/v1/client/fs/logs/" + status["allocation"], text_response=True,
                            type=stream, task=TASK, follow="false", plain="true")

    def cleanup(self, name):
        try:
            self.status(name)
        except ApiError as exc:
            if exc.status == 404:
                return {"job": job_id(name), "state": "absent"}
            raise
        self.request("DELETE", "/v1/job/" + job_id(name), purge="true")
        return {"job": job_id(name), "state": "purge requested"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("environment", help="observe the local host before enrollment (no credentials required)")
    sub.add_parser("ready")
    for action in ("plan", "submit", "status", "wait", "logs", "cleanup"):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument("name")
        if action in ("plan", "submit"):
            p.add_argument("source", help="Python source file, or - for source bytes on stdin")
        if action == "logs":
            p.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    args = parser.parse_args(argv)
    if args.action == "environment":
        print(json.dumps(detect_environment(), sort_keys=True))
        return
    if os.geteuid() == 0:
        raise RuntimeError("Run the batch connector as the provisioned non-root operator")
    cred = ROOT / "connector"
    api = Api(cred, secret_file(cred / "token"))
    def check_identity():
        identity = api.call("GET", "/v1/acl/token/self")
        if (not isinstance(identity, dict) or identity.get("Type") != "client" or identity.get("Policies") != [POLICY]
                or identity.get("Roles") or identity.get("Global")):
            raise RuntimeError("Expected the installed scoped client token")
        return True

    batch = Batch(api)
    if args.action == "ready":
        result = until(lambda: check_identity() and ready(api), 60, "one Raft peer and one eligible, healthy Docker client")
        print(json.dumps({**result, "environment": detect_environment()}, sort_keys=True))
        return
    check_identity()
    if args.action in ("plan", "submit"):
        if args.source == "-":
            source = sys.stdin.buffer.read(49153)
        else:
            with Path(args.source).open("rb") as f:
                source = f.read(49153)
        result = getattr(batch, args.action)(args.name, source)
    elif args.action == "wait":
        result = until(lambda: batch.completed(args.name), 180, "completed allocation")
    elif args.action == "logs":
        sys.stdout.write(batch.logs(args.name, args.stream))
        return
    else:
        result = getattr(batch, args.action)(args.name)
    host = kernel_info()
    print(json.dumps({**result, "platform": host["platform"], "hostname": host["hostname"]}, sort_keys=True))
    if args.action == "plan" and result["placement_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, http.client.HTTPException) as err:
        sys.exit(str(err))
