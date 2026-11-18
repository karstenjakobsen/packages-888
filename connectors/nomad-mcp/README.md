# Nomad local MCP

Prepared connection for a later single-node Nomad installation. This package contains connection metadata and setup instructions; it does not vendor or install an MCP server.

## Current state

- Connection is disabled and untested. No upstream runtime/version has been selected or installed.
- The owner referred to an official Nomad MCP. Research on 2026-11-18 did not verify a HashiCorp-owned implementation. Await its link or the owner's choice before selecting an alternative.
- Community candidate: https://github.com/kocierik/mcp-nomad . This is not HashiCorp-owned. No upstream code was downloaded or executed as part of preparing this connector.
- The reserved executable path /opt/nomad-mcp/bin/mcp-nomad and -transport=stdio invocation are a proposed runtime contract, not evidence that the executable exists. Adapt the committed manifest to the selected implementation if its invocation differs.
- Runtime state, enabled state, credential bindings and worker placement are local; they are not stored in Git.

## Design

The operator launches a stdio MCP process on the Nomad host. /usr/bin/env supplies the nonsecret NOMAD_ADDR=http://127.0.0.1:4646. NOMAD_TOKEN is inherited from the owner's local Connections credential binding. No API or MCP listener is published.

The process must share the host network namespace with Nomad. Loopback in a separate container or host does not address this Nomad agent. Do not use SSH or open a public API to work around worker placement.

Start with a dedicated read-only Nomad ACL token scoped to the required namespace. Never bind the bootstrap management token. Verify the selected MCP's read-only tool filtering at its exact pinned release; ACL permissions enforce the boundary even if tools are advertised.

## Later activation

1. Deploy and verify Nomad using the nomad-single-node skill in ../../skills/nomad-single-node/SKILL.md.
2. Resolve upstream identity; review and pin an exact version/commit and distribution checksum/signature. Record the lock and verification evidence in this package before installation. Keep runtime dependencies and executable outside Git. Install via an authorized operator API task, leaving operator source and dependencies untouched.
3. Verify the executable path, supported stdio flags, environment handling and tool restrictions against that pinned implementation. Commit any manifest changes with project_source tools and refresh the registered connector from its committed package with connector_register_project.
4. The owner supplies/binds the scoped NOMAD_TOKEN in Connections without sharing the token in conversation. The address is already supplied as a nonsecret command argument. Do not disable TLS verification if a future private-network design uses TLS.
5. Enable only when configuration is ready. Run connector_test to discover actual tools. Discovery does not prove API authentication: call a harmless authenticated read such as list_jobs with connector_call after inspecting its real schema.
6. Verify the token's policy denies writes without issuing a cluster mutation; do not use a management token to make discovery pass. Attach the enabled connection to the Nomad project with project_connectors.
7. Report runtime version, actual tool discovery, authenticated read result and checkedAt. This package's current status establishes none of those live checks.

Current checks: connection manifest was inspected as stdio with a loopback API address and no secret value. Runtime initialization and Nomad reachability checks are deferred until the later installation.
