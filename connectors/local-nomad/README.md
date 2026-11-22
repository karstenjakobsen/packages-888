# Local Nomad batch connector

Run `connectors/local-nomad/batch.py environment` on the target before installing Nomad. The action needs only system Python and the reviewed connector files. All other actions run as the provisioned non-root operator and use its private mutual TLS files and scoped ACL token from `/var/lib/catalog-nomad/connector` for HTTPS on `127.0.0.1:4646`. The fixed entrypoint for the example catalog location is `/usr/bin/python3 -ISB /opt/swarm-888/catalog/connectors/local-nomad/batch.py`. [Installer and operator runbook](../../projects/local-nomad/README.md)

| Command | Result |
| --- | --- |
| `environment` | Return read-only host observations from the caller's namespaces and permissions, including before enrollment |
| `ready` | Check for one Raft peer and one eligible client. Return the leader, client node ID, Docker driver health and a nested `environment` report |
| `plan NAME FILE` | Return the plan's existing job index, warnings and placement failures |
| `submit NAME FILE` | Replan and create a new batch job with an atomic create-only precondition |
| `status NAME` | Return job state, latest allocation ID and allocation state |
| `wait NAME` | Return terminal job and allocation IDs and `exit_code: 0` after a verified clean task exit. Failures and timeout exit nonzero |
| `logs NAME [--stream stdout\|stderr]` | Write the task's plain log stream to stdout |
| `cleanup NAME` | Stop and purge the named connector job, or report it already absent |

For typed worker dispatch, map `nomad_batch(action="environment")` to the single argument `environment`, with empty stdin and no enrollment lookup. Run it in the local host worker's namespaces. For `plan` and `submit`, pass `NAME -` and stream up to 49,152 bytes of Python source from the requesting sandbox on stdin. A local operator can pass a file path instead. Names match `[a-z][a-z0-9-]{0,47}`. The only log stream choices are `stdout` (default) and `stderr`. Use direct argv execution and an unprivileged connector process. Keep its token, TLS files and the Docker socket outside ordinary worker sandboxes.

## Environment result

| JSON field | Interpretation |
| --- | --- |
| `hostname`, `architecture`, `kernel_release`, `platform` | The caller's host identity. Platform values are `wsl2`, `wsl1`, `wsl` (WSL evidence with ambiguous generation), `native-linux`, `unknown` (insufficient Linux kernel evidence) and `unsupported` (non-Linux). The classifier reads both proc kernel strings and checks WSL metadata for custom kernels. |
| `systemd.pid1`, `manager`, `ready` (under `systemd`) | PID 1's name and the result of querying the system manager. Readiness requires systemd as PID 1 and a reachable manager. |
| `systemd.docker_unit_load`, `systemd.docker_unit_active` | The local manager's answer for `docker.service`. A confirmed missing unit reports `not-found` in the load field. A failed manager query leaves both fields null. |
| `cgroups.state`, `controllers`, `missing`, `ready` (under `cgroups`) | Observed cgroup v2 controllers and any required controllers missing. An unavailable or unreadable controller file leaves both lists null. |
| `docker.endpoint`, `socket`, `daemon`, `runtime` (under `docker`) | Socket inspection and a single bounded `GET /info` on `unix:///var/run/docker.sock`. Runtime is `docker-desktop`, `linux-engine` or `unknown`. A present socket may return `permission-denied` or `unreachable`. |
| `docker.os_type`, `cgroup_version`, `rootless`, `runc` (under `docker`) | Selected engine facts from the response. Unobserved values are null. |

`environment` exits zero on a partial report. On an unsupported platform the Linux-specific sections are null. `ready` retains its Nomad topology and driver-health checks even when the operator cannot query Docker directly. Other JSON job results include `hostname` and `platform`. Logs remain plain task output so callers can compare an exact marker.

Only the name and literal source bytes vary in the submitted workload. The connector builds the jobspec, embeds the base64 source at a fixed allocation path, and fixes the driver, image, UID, capabilities, mounts and network settings. A token holder who calls Nomad's API directly has the namespace permissions described in the runbook. The HTTPS client connects only to loopback, verifies the installed CA, presents its client certificate and rejects redirects without following their Location.

Commands return JSON except for raw task logs. Errors go to stderr and exit nonzero. Each program runs inside the packaged Python Docker image with an isolated network namespace. Job IDs use the prefix `project-` inside the dedicated `catalog-projects` namespace. [Nomad job operations](https://developer.hashicorp.com/nomad/api-docs/jobs) · [Client log API](https://developer.hashicorp.com/nomad/api-docs/client#stream-logs)
