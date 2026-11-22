---
name: local-nomad
description: Detect the local WSL or native Linux environment, install and operate the catalog's persistent Nomad service, and run and verify small Python batch workloads through its Docker connector.
---

# Local Nomad

Prefer the typed tools offered by `swarm_host`. Before enrollment or installation, call `nomad_batch(action="environment")` on the target host. The CLI equivalent is `connectors/local-nomad/batch.py environment`. It needs no Nomad credentials. Use the returned `platform`, `hostname`, `docker`, `systemd` and `cgroups` to choose the next step.

- On `wsl1`, report the WSL2 conversion prerequisite. For ambiguous `wsl`, confirm the distribution version with `wsl --list --verbose` on Windows. On `wsl2`, check systemd in the distribution and the existing Linux Docker socket. A reachable Docker Desktop engine can serve jobs with `docker_unit_load="not-found"`.
- On `native-linux`, check the observed systemd manager, cgroup controllers and local engine. For `unknown` or `unsupported`, report the observation and confirm the target. When the operator lacks socket or manager access, use the root worker's authorized preflight for those facts. Keep the existing engine and sandbox permissions.

Use `nomad_service` for authorized checks, installation and service lifecycle. Use `nomad_batch` for batch operations according to its advertised schema. Local workers already have the prescribed privileges. The root deployment worker runs `check` and `install` from its reviewed immutable copy with the configured operator account. Preserve conflicting deployments. Retry an interrupted install with the same account. Restore missing administrator credentials or Raft state from a matching private backup. The runbook covers offline tests, worker commands and restart verification. [Operator runbook](../../projects/local-nomad/README.md)

If the batch tool is unavailable, the provisioned operator can run `connectors/local-nomad/batch.py`. The CLI reads its scoped token and TLS files directly. For CLI submission from a sandbox, pass `NAME -` and stream the source bytes on stdin. Keep credentials out of shell arguments, environment dumps, logs, job source and the checkout.

- Run `ready` after starting or restarting the service. Expect one Raft peer and one eligible client with a healthy Docker driver. Include the observed hostname and platform in task results, along with the allocation ID and verified output for a completed job. Report Docker runtime identity only when the probe could read it.
- For a project, review the Python file and choose a fresh short lowercase job name. Run `plan NAME FILE`, inspect placement failures, then `submit NAME FILE`. Submission is create-only. If the response is interrupted, inspect `status NAME` before retrying.
- Use `wait NAME` for allocation completion and `logs NAME` for stdout. Use `logs NAME --stream stderr` on failure. Verify the workload's expected result before reporting success. `projects/local-nomad/smoke.sh` does this for the packaged example.
- Use `cleanup NAME` to stop and purge that job after collecting evidence. To execute the same program again, use a new name or purge the old job first. Retain the private state directory across service restarts.

The connector builds a non-root, network-isolated Docker task from source and a pinned Python image. It accepts small, self-contained programs. Jobs that need additional runtimes, secrets, services or host resources need a separately reviewed workload design.
