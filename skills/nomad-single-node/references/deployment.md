# Later installation procedure

The supplied JSON is Nomad agent configuration, not a job specification. All control endpoints are explicitly loopback. The workload interface is independent: approving a workload with published ports requires its own ingress decision.

1. Check disk space and memory; reserve capacity for the OS, Docker and operator after observing host usage. Choose workload CPU/memory limits accordingly.
2. Install an exact approved Nomad Community binary/package from HashiCorp with signature/checksum verification. Inspect package units/default config before starting anything. Ensure defaults cannot start a publicly listening agent during installation.
3. Prepare /etc/nomad.d and /var/lib/nomad (or approved equivalents) with restricted ownership. The combined agent contains a Linux client and normally needs root for cgroups and Docker integration. Root authorization must come from the deployment task. Do not add hardening options such as PrivateMounts or ProtectControlGroups without checking client compatibility.
4. Adapt the provided unit or a compatible vendor unit. Its ExecStart binary must match the installed path. The unit belongs to this Nomad project, outside the operator core. It runs persistently with Docker ordering and process-only shutdown. If using project_deploy instead, provide the supported project run manifest and inspect its generated service for equivalent client requirements; do not create two competing Nomad services.
5. Run nomad config validate /etc/nomad.d with the selected version. Validate the unit with systemd-analyze verify. Offline JSON checks are supplemental and cannot replace Nomad's parser.
6. Start the service only in the later authorized installation task. Check systemctl status/is-active/is-enabled and bounded logs; do not copy credentials from logs to chat.
7. Set NOMAD_ADDR=http://127.0.0.1:4646 only for authorized same-host commands. Bootstrap ACLs once on a genuinely new cluster, capturing sensitive output directly into a protected runtime file/credential workflow with restrictive umask. If already bootstrapped, use the existing authorized credential; do not reset bootstrap. The owner configures credentials in Connections; never request token values in conversation.
8. Use the management credential only to establish narrowly scoped policies/client tokens. references/mcp.md includes an initial observation policy. Keep bootstrap credentials protected outside Git and outside ordinary MCP access.
9. Observe leader and peers with nomad server members and nomad operator raft list-peers; observe one ready client using nomad node status and inspect Docker driver health. Use authorized ACL credentials without printing them.
10. Inspect ss -lntup and service configuration: 4646/TCP, 4647/TCP, 4648/TCP+UDP must not listen on wildcard/public IPv4 or IPv6. Inspect reverse proxies, container publication and firewall/NAT redirection for indirect exposure. Keep firewall protections as defense in depth without changing unrelated policy. Probe public interfaces externally when possible.
11. Check an ACL-protected endpoint (for example GET /v1/jobs) returns denial without a token and succeeds with the dedicated observation token. Leader/status endpoints may be readable without a token; they do not prove ACL failure.
12. Submit a small Docker batch job using an approved exact image digest, no published ports, no host volumes and no privileged mode. Wait for successful completion and inspect allocation/driver events. Clean up only that smoke job. Bridge-mode jobs require compatible CNI plugins and kernel networking; verify/install those only when that network mode is needed. No Consul or Vault installation is implied.
13. Verify restart persistence in a bounded maintenance window, including re-election and node/driver health. Avoid a host reboot without separate need/authorization. Register service state through project components and project_refresh where supported.

On failure, stop the newly created service and retain data for diagnosis. Restore prior config/unit/binary only when compatible and reviewable. Do not delete data_dir, reset Raft or downgrade persisted state speculatively. Stopping a client with KillMode=process can leave allocations/containers running; inspect and report them and stop only allocations owned by this task when cleanup is authorized.

Sources checked 2026-11-18; recheck against selected version:
- [Agent configuration and merge behavior](https://developer.hashicorp.com/nomad/docs/configuration)
- [Explicit advertise normalization](https://github.com/hashicorp/nomad/blob/main/command/agent/config.go)
- [Server configuration](https://developer.hashicorp.com/nomad/docs/configuration/server)
- [Docker driver](https://developer.hashicorp.com/nomad/docs/deploy/task-driver/docker)
- [Client networking](https://developer.hashicorp.com/nomad/docs/configuration/client)
- [Service example and client privileges](https://developer.hashicorp.com/nomad/tutorials/enterprise/production-deployment-guide-vm-with-consul) (use service mechanics, not Enterprise/Consul topology)
- [ACL bootstrap](https://developer.hashicorp.com/nomad/docs/secure/acl/bootstrap)
