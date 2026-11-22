# Local Nomad operator runbook

One enabled systemd service runs a Nomad Community Edition 2.1.1 agent as both the sole Raft server and the sole scheduling client. Control traffic stays on IPv4 loopback. The local Docker daemon runs project code. Losing this machine or its Raft data takes down the cluster. [Agent configuration](https://developer.hashicorp.com/nomad/docs/configuration) · [Server configuration](https://developer.hashicorp.com/nomad/docs/configuration/server)

## Root worker contract

The privileged deployment worker executes the reviewed installer from a root-owned immutable catalog copy. The examples use `/opt/swarm-888/catalog` for that copy. Its absolute location is configurable at provisioning time. Preserve the relative layout below and keep the snapshot and its parent directories outside worker-writable paths. Give the batch account read access to the public connector files and traversal access to their parent directories.

| Consumer | Required files relative to the catalog root |
| --- | --- |
| Installer | `projects/local-nomad/install.py`, `projects/local-nomad/release.py`, `projects/local-nomad/agent.hcl.in`, `projects/local-nomad/catalog-nomad.service`, `connectors/local-nomad/nomad_api.py`, `connectors/local-nomad/host_environment.py` |
| Operator connector | `connectors/local-nomad/batch.py`, `connectors/local-nomad/nomad_api.py`, `connectors/local-nomad/host_environment.py` |
| Live acceptance | `projects/local-nomad/smoke.sh` and `projects/local-nomad/examples/squares.py`, alongside the connector |
| Operator instructions | `skills/local-nomad/SKILL.md` and the project and connector READMEs |

Use these argv vectors for the two installer operations. The worker resolves the snapshot path and account from trusted provisioning configuration and dispatches the selected operation directly.

```text
["/usr/bin/python3", "-ISB", "/opt/swarm-888/catalog/projects/local-nomad/install.py", "check", "--operator", "nomad-operator"]
["/usr/bin/python3", "-ISB", "/opt/swarm-888/catalog/projects/local-nomad/install.py", "install", "--operator", "nomad-operator"]
```

Run with effective UID 0, working directory `/`, stdin from `/dev/null`, and a fresh environment containing `PATH=/usr/sbin:/usr/bin:/sbin:/bin` and `LC_ALL=C`. The interpreter runs in isolated mode with site initialization and bytecode writes disabled. `--operator ACCOUNT` is required for both operations. Supply the existing non-root Unix login name that should own the connector credentials. On a VPS, provision that account before dispatch and supply its configured name in place of the example `nomad-operator`. The installer records the resolved UID for retries. A successful `check` returns JSON with `check="passed"` and the root worker's `environment`. A successful `install` returns Nomad readiness and the root worker's preflight environment after credential provisioning. Failures exit nonzero with diagnostics on stderr.

## Identify the host before installation

Dispatch `nomad_batch(action="environment")` through the host adapter when offered. Its complete argument vector follows. This read-only probe runs before enrollment without an operator token, Nomad connection or root privileges.

```sh
/usr/bin/python3 -ISB /opt/swarm-888/catalog/connectors/local-nomad/batch.py environment
```

Record `hostname` and `platform` in the task result. On `wsl1`, check the distro name with `wsl --list --verbose` on Windows and convert the intended distro with `wsl --set-version <Distro> 2` before installation. For generic `wsl`, use the same listing to confirm the generation. On WSL2 with systemd disabled, enable `[boot]` with `systemd=true` in the distro's `/etc/wsl.conf`, then restart the distribution during a maintenance window. On `native-linux`, check the local system manager. The probe makes no distinction between a native Linux VM and a physical machine. [WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) · [WSL systemd configuration](https://learn.microsoft.com/en-us/windows/wsl/systemd)

Read `docker.runtime` separately. A system reporting `docker-desktop`, a reachable daemon and `systemd.docker_unit_load="not-found"` can pass the root worker's checks. The unit keeps native startup ordering with `After=docker.service` and uses the existing socket on both paths. When the probe runs inside a sandbox, PID 1, systemd and the socket reflect that sandbox's view. A permission denial leaves the runtime or Docker unit identity unknown. Inspect the root worker's `check` on the target to resolve it. [Connector result fields](../../connectors/local-nomad/README.md#environment-result)

## Host requirements

- Use x86-64 Ubuntu 24.04 with native systemd, Python 3.10+ at `/usr/bin/python3`, GnuPG, system CA certificates, and cgroups v2 with `cpu`, `cpuset`, `io`, `memory`, and `pids`. The Linux state filesystem must support execution and Nomad allocation mounts. [Nomad installation requirements](https://developer.hashicorp.com/nomad/docs/deploy/production/requirements)
- The installer queries the Docker Engine API directly at `/var/run/docker.sock`. For a WSL2 host using Docker Desktop, enable its WSL 2 engine, Linux containers and integration for the Ubuntu distribution. For a host using Linux Engine, make the existing daemon available at the same socket. Both paths require a rootful Linux engine with cgroup v2 and the runc runtime. Only the Nomad unit is installed. On WSL, it starts with the distribution's systemd. Docker Desktop has its own startup lifecycle. [Docker Desktop WSL integration](https://docs.docker.com/desktop/features/wsl/) · [Nomad Docker driver](https://developer.hashicorp.com/nomad/docs/deploy/task-driver/docker)
- Provide free loopback TCP ports 4646 (HTTPS), 4647 (RPC), 4648 (Serf), and UDP 4648. Allow HTTPS to the HashiCorp release and signing-key hosts for first installation. Docker needs to pull the pinned Python image or have its exact digest cached. Reserve 200 MHz CPU, 96 MiB memory and 64 MiB allocation disk for the sample, plus space for the agent, downloads, Docker layers and Raft state. The Engine must resolve the WSL allocation bind mounts. The smoke test exercises this by executing the source file Nomad renders in the allocation. [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/) · [Image digest source](https://github.com/docker-library/repo-info/blob/master/repos/python/remote/3.13-alpine.md)

`check` inspects host prerequisites, ownership and listeners. `install` downloads the Linux AMD64 zip into a private temporary directory under `/var/lib`. It verifies the checksum manifest's detached signature with a temporary GnuPG keyring, checks the signer's full HashiCorp fingerprint and compares the exact archive against both the signed entry and the catalog's SHA-256 pin. Only the Nomad executable is extracted. Installation validates the generated config with that executable before enabling the unit. [Release and signature](https://releases.hashicorp.com/nomad/2.1.1/) · [Pinned checksum](https://releases.hashicorp.com/nomad/2.1.1/nomad_2.1.1_SHA256SUMS) · [HashiCorp signing key](https://www.hashicorp.com/en/trust/security) · [HashiCorp verification procedure](https://developer.hashicorp.com/terraform/tutorials/cli/verify-archive)

A running unmanaged Nomad agent or a conflict with an existing `nomad.service`, standard Nomad config/data directory, target unit/override, catalog state tree, or occupied port stops installation. Inspect the named conflict. The package has its own installation path and never adopts a running agent. Run a retry with the same operator. Installation serializes concurrent runs, reuses the installed binary, checks its recorded hash and preserves the CA, cluster identity, data and tokens. Changing operator or upgrading the pinned version requires a separate migration.

## Run and verify a job

Run the live acceptance commands as the provisioned non-root operator after the worker reports installation success.

```sh
catalog=/opt/swarm-888/catalog
batch="$catalog/connectors/local-nomad/batch.py"
"$batch" ready
"$catalog/projects/local-nomad/smoke.sh"
```

`smoke.sh` chooses a fresh name, plans and submits the packaged calculation, waits up to three minutes for allocation completion, checks exact stdout, then purges its job. If acceptance fails, the job remains available for diagnosis. To inspect each step manually, run the following in the same shell.

```sh
name="squares-$(cat /proc/sys/kernel/random/uuid)"
source_file="$catalog/projects/local-nomad/examples/squares.py"
"$batch" plan "$name" "$source_file" &&
  "$batch" submit "$name" "$source_file" &&
  "$batch" status "$name" &&
  "$batch" wait "$name" &&
  "$batch" logs "$name" &&
  test "$("$batch" logs "$name")" = 'sum-of-squares=338350' &&
  "$batch" cleanup "$name"
```

The sample computes the sum of the first 100 positive integer squares. `submit` returns an evaluation ID. `wait` requires a terminal job, a completed allocation and a dead, successful Python task with a recorded zero exit code and signal. `status` identifies that allocation. `logs NAME --stream stderr` retrieves error output. Read the logs before cleanup or Nomad's allocation garbage collection. After submission a failed task stays failed for inspection. Placement failures appear in the plan. If the submit response was interrupted, inspect the job by name. A zero modify-index precondition prevents concurrent creation or an accidental update. Submit a fresh name for another run, or clean up the original first. [Jobs API](https://developer.hashicorp.com/nomad/api-docs/jobs) · [Task state and termination events](https://developer.hashicorp.com/nomad/api-docs/allocations) · [Allocation log stream](https://developer.hashicorp.com/nomad/api-docs/client#stream-logs)

For your own batch workload, replace the example file with a self-contained Python program of up to 48 KiB. Names start with a lowercase letter and allow lowercase letters, digits and hyphens. Source travels in the job specification and is visible to users with job-read access. Keep secrets out of it. The connector always builds one non-root task with a digest-pinned image, all capabilities dropped, no new privileges, no network or published ports, a read-only root filesystem, and CPU, memory and process limits. Nomad supplies its standard allocation, task and secrets directories. The client allows only the Docker driver, disallows privileged containers and host bind paths, and restricts namespace sharing. Use this interface for trusted project submitters. The underlying Nomad registration permission allows jobs throughout the project namespace and does not enforce the connector's Python template. [Client driver allowlist](https://developer.hashicorp.com/nomad/docs/configuration/client) · [Docker task configuration](https://developer.hashicorp.com/nomad/docs/job-declare/task-driver/docker)

## Service lifecycle and restart test

The privileged worker can map its authorized lifecycle operations to fixed system commands for the installed `catalog-nomad.service`. For example, the restart argv is `["/usr/bin/systemctl", "--no-ask-password", "restart", "catalog-nomad.service"]`. Use the same fixed unit with `start` and `stop`. For an intentional change to boot policy use `disable --now` or `enable --now`. Gate service mutations on the worker's ownership of the installed unit. The root installer enables it at installation. Read status with `/usr/bin/systemctl status --no-pager catalog-nomad.service` and diagnostics with `/usr/bin/journalctl -u catalog-nomad.service -n 80 --no-pager`.

Stopping the agent pauses scheduling. Use job cleanup to stop a workload. A single-server restart briefly takes the control plane offline. For a persistence test, keep this operator shell open across the root worker's restart:

```sh
name="restart-$(cat /proc/sys/kernel/random/uuid)"
ready_node() {
  ready_json=$("$batch" ready) &&
    /usr/bin/python3 -ISB -c 'import json, sys; print(json.loads(sys.argv[1])["node"])' "$ready_json"
}
before=$(ready_node) &&
  "$batch" submit "$name" "$catalog/projects/local-nomad/examples/squares.py" &&
  completed_before=$("$batch" wait "$name")
```

After those commands succeed, dispatch the typed restart and wait for the worker to finish. In the same non-root shell, verify the same node, allocation and result:

```sh
after=$(ready_node) &&
  test "$after" = "$before" &&
  completed_after=$("$batch" wait "$name") &&
  test "$completed_after" = "$completed_before" &&
  test "$("$batch" logs "$name")" = 'sum-of-squares=338350' &&
  "$batch" cleanup "$name"
```

On failure, the job remains available for inspection and manual cleanup. Readiness requires the loopback leader, one Raft peer and one eligible, ready client with a healthy Docker driver. On timeout, inspect the unit journal, Docker socket availability, host cgroups and image pull access. If the task cannot read `project.b64` on WSL, inspect Docker Desktop integration and the allocation directory bind mounts. [Status API](https://developer.hashicorp.com/nomad/api-docs/status) · [Nodes API](https://developer.hashicorp.com/nomad/api-docs/nodes)

## State and credentials

| Location | Purpose and access |
| --- | --- |
| `/etc/systemd/system/catalog-nomad.service` | Dedicated root-owned boot unit |
| `/var/lib/catalog-nomad/private` | Root-only binary, agent config with random gossip key, installation record, CA/signing key, server and CLI TLS material, and `management.token` |
| `/var/lib/catalog-nomad/private/data` | Persistent server and client identity, Raft, ACLs and allocation state |
| `/var/lib/catalog-nomad/connector` | Operator-readable TLS client files and `token`, mode 0400, in a root-controlled directory |

Mutual TLS protects HTTPS from the first startup. RPC verifies the server identity, and Serf uses the generated gossip key. The installer prewrites the bootstrap UUID privately, verifies its identity on retry and never performs an ACL reset. A stable installation-specific token name lets it recover a committed connector token after a lost response. On an established cluster the installer checks for its Raft database and private credentials before startup. A revoked connector token requires operator recovery. Installation also checks that anonymous node reads and connector access to the administrator token list are denied. The client policy grants plan, register, read, read-logs and purge in `catalog-projects`, plus node read for readiness. The root administrator credential stays under `private`. [Nomad TLS](https://developer.hashicorp.com/nomad/docs/secure/traffic/tls) · [ACL bootstrap](https://developer.hashicorp.com/nomad/docs/secure/acl/bootstrap) · [ACL tokens API](https://developer.hashicorp.com/nomad/api-docs/acl/tokens) · [ACL capabilities](https://developer.hashicorp.com/nomad/docs/secure/acl/policies) · [Namespaces API](https://developer.hashicorp.com/nomad/api-docs/namespaces)

Keep a protected off-host backup of the private credentials and matching cluster state. A cold filesystem backup should be made with workloads finished and the agent stopped, preserving ownership and modes. Restore the matching state and credentials together. Keep release archives, private backups and token values outside the catalog. Leaf certificates issued by the Nomad CLI default to one year. Check expiry with `openssl x509 -in /var/lib/catalog-nomad/connector/global-cli-nomad.pem -noout -enddate`. Renew server and CLI certificates under the existing CA in a private staging directory, replace the corresponding root-only copies during maintenance, restart the unit and rerun the installer to refresh the operator copies. [Certificate issuance and TLS configuration](https://developer.hashicorp.com/nomad/docs/secure/traffic/tls)

## Workspace tests

```sh
/usr/bin/python3 -B -m unittest discover -s projects/local-nomad/tests -v
```

The suite uses temporary files and simulated Nomad responses. It runs the generated Python arguments locally, checks the example output, and exercises release-verification decisions, private credential handling, interrupted provisioning, conflict rejection, readiness, submission, logs and cleanup. For a release-backed offline test, point `NOMAD_TEST_RELEASE_DIR` at a directory outside Git containing `hashicorp.asc` (the official public key), `nomad_2.1.1_SHA256SUMS`, `nomad_2.1.1_SHA256SUMS.72D7468F.sig`, and `nomad_2.1.1_linux_amd64.zip`. Rerun the same suite. It verifies the signed archive, rejects a damaged signature, generates certificates in a temporary directory, validates the agent config and renders the job with the pinned CLI. Live acceptance requires the install and smoke commands above.
