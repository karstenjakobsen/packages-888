# Official upstream setup

Use [DigitalOcean MCP v1.4.1](https://github.com/digitalocean-labs/mcp-digitalocean/releases/tag/v1.4.1), commit `13aff3d1cb9bda29e09a257bff5a8a2fc08e6717`. Verify the official prebuilt archive for the worker's platform against both the release checksum file and GitHub asset digest. Extract once into a durable versioned runtime outside tracked source. Linux amd64 SHA-256 values:

- Archive `mcp-digitalocean_1.4.1_linux_amd64.tar.gz`: `994ec1e56892d51f86e8100ae20c0a001dad85ce1f7a930d5a2413c232ba1d72`.
- Published checksum list: `c5c4f7702cf4886b840c3e57dfa66a148ad75fa10586e98b33441717ffd84c6d`.
- Executable `mcp-digitalocean-linux-amd64`: `28c9885125cbd71e4bd6edb74496be4f18bafcc827a79a3e98749321a02ca350`.

Register the executable directly as stdio with `--services networking --transport stdio`, using the default provider endpoint. Keep it disabled until the owner configures authentication and authorizes a read-only test. Look up machine-specific installation and connection details in checked operator memory. Offline discovery can use a clean subprocess environment, a nonsecret placeholder token in `DIGITALOCEAN_API_TOKEN` and a loopback reject/recording endpoint set via `DIGITALOCEAN_API_ENDPOINT`. Send initialize, notifications/initialized and tools/list following any cursors. Close stdin and assert clean exit and zero requests. Keep the placeholder and loopback endpoint confined to the probe.

## Owner credential setup and first read

1. Generate a personal access token in DigitalOcean **API → Tokens** using **Custom Scopes** and `domain:read`. Add `domain:create` only when live record creation is authorized. That scope also permits creating domains and requires `domain:read`. Leave update and delete scopes out. [Read scope](https://docs.digitalocean.com/reference/api/scopes/domain/read/) · [Create scope](https://docs.digitalocean.com/reference/api/scopes/domain/create/)
2. Open operator **Connections → DigitalOcean DNS → Authentication**. Select **Environment variables** and **Create a new credential**. Name it **DigitalOcean DNS credential**, use field name `token` and enter the token in **Secret value**. Set **Environment bindings (JSON)** to `{"DIGITALOCEAN_API_TOKEN":"token"}`. Click **Save credentials & binding**.
3. For separately authorized verification, click **Enable connection**, then **Test connection** for tool discovery. Grant the connection to the normal-user verification task and identify one existing zone. Use `domain-get` and paginate `domain-record-list` for that zone. Report protocol discovery and provider read success separately.

## Observed v1.4.1 DNS input schemas

Inputs are case-sensitive and required unless marked optional.

| Tool | Inputs |
| --- | --- |
| `domain-get` | `Name` string |
| `domain-list` | Optional numeric `Page` (1), `PerPage` (20) |
| `domain-record-list` | `Domain` string, optional numeric `Page` (1), `PerPage` (20) |
| `domain-record-get` | `Domain` string, numeric `RecordID` |
| `domain-record-create` | `Domain`, `Type`, `Name`, `Data` strings |
| `domain-create` | `Name`, `IPAddress` strings |
| `domain-delete` | `Name` string |
| `domain-record-edit` | `Domain`, `Type`, `Name`, `Data` strings, numeric `RecordID` |
| `domain-record-delete` | `Domain` string, numeric `RecordID` |

The last four tools are outside default scope. [Pinned DNS handlers](https://github.com/digitalocean-labs/mcp-digitalocean/blob/v1.4.1/pkg/registry/networking/domains_tools.go)
