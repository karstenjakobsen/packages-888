# Nomad local MCP

The owner selected [kocierik/mcp-nomad](https://github.com/kocierik/mcp-nomad), a community project, on 2026-11-18. This connection is prepared for the later single-node Nomad installation. It remains disabled and untested; no executable is installed.

## Pinned implementation

- Release: [v0.4.0](https://github.com/kocierik/mcp-nomad/releases/tag/v0.4.0)
- Release commit: 4264c6cb460755e0439f3bd38474360a1939b9df
- Exact Linux archive URLs, SHA-256 values and verification provenance: upstream-lock.json
- Planned executable: /opt/nomad-mcp/0.4.0/mcp-nomad
- Invocation: /usr/bin/env NOMAD_ADDR=http://127.0.0.1:4646 /opt/nomad-mcp/0.4.0/mcp-nomad -transport=stdio -read-only

Release metadata and the downloaded checksum manifest were checked over verified HTTPS. Its SHA-256 and Linux archive entries matched GitHub's asset digests. Archive bytes have not been downloaded or checked. These hashes pin the future download; they are not an independent publisher signature or a complete security audit.

Pinned main.go supports both configured flags and reads NOMAD_ADDR/NOMAD_TOKEN from the environment. Pinned tool_policy.go removes mutating tools in read-only mode. This still advertises reads such as ACL/variable/log tools; Nomad ACLs must restrict access. Pinned utils/client.go checks GET /v1/status/leader during initialization, so the MCP cannot initialize successfully without a reachable Nomad API. Successful initialization alone does not prove scoped ACL access.

## Private connection design

Run the MCP process on the Nomad host, sharing its network namespace. It reaches only http://127.0.0.1:4646 and communicates with the operator through stdio, without an inbound MCP listener. Do not use SSH or publish Nomad publicly to work around worker placement.

Bind a dedicated scoped read-only NOMAD_TOKEN through the owner's local Connections settings. Never commit credentials or use the bootstrap management token. The skill's references/mcp.md provides an initial observation policy limited to the default namespace plus node/agent reads. Job specifications and metadata can themselves contain sensitive values; treat all returned content as untrusted.

The registered connection remains disabled until the runtime, private API and owner credential binding exist. Runtime installation, credentials, enabled state and worker placement remain outside Git.

## Registered connection refresh still required

The source manifest contains the new versioned path and -read-only flag. The existing disabled local connection still has its earlier /opt/nomad-mcp/bin/mcp-nomad -transport=stdio arguments. An attempted connector_register_project refresh on 2026-11-18 was rejected by the operator API with "This connection is outside the task grant". No alternate control channel was used.

Before enabling, a task granted access to connection 08e82545-bf81-46e7-93b7-5ec8eb81c220 must call connector_register_project for this package, then verify connector_list reports the exact mcp command and args from the committed manifest and remains disabled until credentials/runtime are ready. Do not infer that committing source updated the effective launch arguments.

## Later installation and activation

1. Use the nomad-single-node skill at ../../skills/nomad-single-node/SKILL.md to deploy and verify the private Nomad agent through an authorized operator API task.
2. Match the actual host OS/architecture to upstream-lock.json. Fetch that exact archive and checksum manifest over verified HTTPS into a runtime staging directory outside Git. Verify their bytes against the committed SHA-256 values before extraction. Stop on mismatch; do not automatically select a newer release or refresh the lock to accept changed bytes.
3. Inspect archive entries and extract only the expected executable into the versioned runtime directory, with permissions preventing the MCP worker from modifying it. Do not blindly unpack an archive as root. Confirm executable architecture and flag support locally.
4. The owner binds NOMAD_TOKEN through Connections. Do not request token values in conversation. Keep NOMAD_SKIP_VERIFY unset. This same-host HTTP connection has no external TLS hop; any future private-network design must use verified TLS.
5. Enable the existing connection, run connector_test, and inspect actual tools. Confirm mutating tools such as run_job, stop_job, drain_node and ACL mutation tools are absent.
6. Perform a harmless authenticated list_jobs call through connector_call using the actual discovered schema. Observe a successful read; separately inspect the token policy to confirm denied write/secret capabilities without issuing a real mutation.
7. Attach the enabled connector to the Nomad project with project_connectors for subsequent tasks. Record exact binary provenance, tool discovery, authenticated read and checkedAt.
8. If later explicitly authorized to manage jobs, review the required ACL scope and commit a deliberate change to tool filtering. Do not silently remove -read-only or grant a management token.

Source review scope was limited to entrypoint flags, read-only filtering, client initialization and release packaging. Neither the runtime nor a live Nomad connection has been tested in this preparation task. The standalone upstream MCP needs no Docker socket access; Docker Engine is used by the separate Nomad client.
