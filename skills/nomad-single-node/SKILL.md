---
name: nomad-single-node
description: Prepare, install and verify a persistent single-node HashiCorp Nomad server/client using Docker Engine, a private API and an operator MCP connection.
---

Use for a requested single-host Nomad deployment. Creating or reading this skill does not authorize installation. The current owner request is preparation for later installation; no backups are requested.

## Deployment contract

- Run one persistent agent as server and client with bootstrap_expect=1; never use agent -dev for an installed service.
- Use the existing Docker Engine Unix socket. Keep Docker's TCP API disabled.
- Bind HTTP 4646, RPC 4647 and Serf 4648 to 127.0.0.1 and explicitly advertise loopback for this same-host topology. Do not create a public DNS name, reverse proxy, published Docker port or public firewall allowance for these services. IPv6 must not expose them either.
- Enable Nomad ACLs. MCP receives a dedicated scoped token, never the bootstrap management token. Secrets remain outside Git and chat.
- Backups are deferred by owner choice. Persistent disk is not a backup; this deployment has neither failover nor a promised recovery point. Do not add backup jobs or block deployment solely because backups are deferred.
- Keep the MCP on the same host/network namespace as Nomad using stdio. This requires no inbound MCP listener. A connector running in a container cannot reach the host using its own 127.0.0.1.
- Combined server/client is a deliberate small-installation tradeoff. It is supported but not HashiCorp's recommended production architecture.

## Before a later installation

Use authorized tasks through the verified TLS operator API for host operations; never SSH. Inspect actual privileges, OS/architecture, resources, existing Nomad/Docker services, active configuration, listener ownership and firewalls. Preserve existing Docker workloads and unrelated services.

Search project_list, repository_list, package_list and connector_list for existing entries. Register a Nomad project in an owner-supplied or existing registered repository before authoring or deploying. Keep authored source within its assigned source.workspacePath and commit through project_source tools. Register service and script components and checkpoint milestones.

Select a supported Nomad version at execution time from official releases and read its matching documentation. Pin its exact version and verify repository signatures or signed release checksums. Inspect the existing Docker installation; install or alter dependencies only as authorized for this deployment. Do not upgrade the host or reinstall Docker incidentally.

## Stage and start

Read [references/deployment.md](references/deployment.md). Use assets/nomad.json and assets/nomad.service as starting material, not as proof of compatibility. Adjust the binary path and approved data path to the actual host. Store mutable Nomad state, container data, downloaded binaries and credentials outside source control.

Inspect every loaded .hcl/.json file and service override: Nomad merges configuration, so checking a single template does not establish effective settings. Stage one coherent config, validate it with the selected binary, and review the diff before activation. Do not overwrite unknown existing Nomad state.

## Verify and hand off

Require observed service health, one elected server, one ready Docker-capable client, ACL enforcement, loopback-only listeners and a successful Docker smoke allocation. Check privacy from an external vantage when available; report missing external verification. Do not claim installation succeeded from an offline fixture.

Read [references/mcp.md](references/mcp.md) when preparing or activating the connector. Leave it disabled until runtime, credentials and private reachability are configured. Test MCP discovery separately from an authenticated read. Attach enabled connections to the Nomad project for subsequent tasks.

Report source commit and publication state separately from deployment and observed health. Record exact versions, checkedAt, deferred backups, connector state and any missing checks. Do not record a successful live skill outcome until the procedure has actually been used.
