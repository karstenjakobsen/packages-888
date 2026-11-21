# Money — Bilance POC
Target: https://money.karstenjakobsen.dk
Loopback service: 127.0.0.1:3187. Persistent runtime data: /home/swarm/packages/4c2d0475-8c2c-4dd5-a040-c84f3d543ac6/money-data.
No production finance data is bundled. The explicit sample view is browser-only.

## Activation gates
1. In operator Connections, authorize official Bilance connection 5d1f6428-8b8a-4fdf-bde4-717669b9eb17 through OAuth. Bilance has NO API key/password fields. Endpoint: https://mcp.bilanceapp.com/mcp. If operator Connections cannot complete MCP OAuth, an owner-maintained operator release is required; do not substitute a scraped session token.
2. Grant that connection and DigitalOcean DNS to a new project task. This initial task has no connector grants; project assignment and DNS calls were rejected.
3. Configure a dashboard password using configure-password.mjs, supplied on stdin from an owner-configured credential. The helper writes only a salted scrypt hash outside Git. Do not send credentials through chat. A runtime settings.json placeholder is automatically created with an empty passwordHash. There is no credential creation/binding tool available to this task.
4. After OAuth, discover actual tools, call get_finance_context, verify the account, and read current-month summaries/categories/budgets/accounts/transactions using their actual schemas. Respect Copenhagen month boundaries, Bilance default currency, exclusions and household scope. Never derive totals from a truncated transaction page. Do not call mutation/bank-refresh tools. Normalize to the snapshot schema, record checkedAt and transactionsComplete, and pipe to import-snapshot.mjs. Unknown fields or amounts block activation; do not invent them.
5. Add A money -> 212.132.68.43 through granted DNS connection after conflict checks. Authoritatively verify all delegated nameservers. No AAAA. At initial check, public Google DNS returned no A/AAAA/CNAME.
6. Provision a money-only Caddy route proxying 127.0.0.1:3187. The existing /etc/caddy/swarm-888.Caddyfile belongs to operator ingress and must remain untouched. Use an owner-approved separate ingress integration or external release to import the money route; no operator startup/config edits.

## Normalized snapshot v1
Required fields: version=1, source=Bilance, month=YYYY-MM (current Europe/Copenhagen month), currency=ISO 4217, checkedAt=ISO timestamp, income>=0, expenses>=0, transactionsComplete=boolean.
Arrays: categories [{name,amount>=0}], transactions [{date:YYYY-MM-DD,description,category,amount:signed}], accounts [{name,balance}], budgets [{name,spent>=0,limit>0}].
All figures must use one default currency; exclude transfers/excluded items from analytics. Category amount is expense magnitude. Income and expenses are authoritative Bilance summary totals. Empty arrays mean unavailable/no items, never fabricated records.
The importer validates and atomically replaces private snapshot.json. Old-month snapshots are refused. Dashboard shows the observation time and completeness. There is no automatic sync until OAuth is verified and a job is explicitly configured.

## Validation and runtime
node --test service.test.mjs
The service runs as a managed independent systemd service via project_deploy. UI and health are public; financial API is password gated, fails closed, never serves the credential file, and uses Secure/HttpOnly/SameSite cookies, origin checks, no-store and a strict CSP.
Buildless Node, no external dependencies. Session memory expires after one hour; restart signs users out.
