---
name: ubuntu-fail2ban
description: Plan and verify narrowly scoped Fail2ban SSH protection on Ubuntu with explicit live-change authorization and a recovery path.
---

# Ubuntu Fail2ban for SSH

Use this procedure for SSH authentication failure rate limiting through Fail2ban. Broader OS hardening requires its own assessment. The documented baselines are Ubuntu 22.04 LTS (Jammy, Fail2ban manual package 0.11.2-6) and Ubuntu 24.04 LTS (Noble, 1.0.2-3ubuntu0.1). Confirm the actual package revision, shipped config and command syntax on each target. Other releases require the same checks against their own documentation. This bundle's checks exercise the Python renderer only. No Ubuntu/Fail2ban combination was exercised natively.

## Read-only discovery

- Read the target's OS release metadata. Use `dpkg-query -W fail2ban openssh-server` and, when installed, `fail2ban-client --version`; use `apt-cache policy fail2ban` for existing local package metadata if absent. Record config root, socket, service manager, unit and overrides from the process and unit definitions. On systemd inspect unit listings, `systemctl cat`, `systemctl show`, active and enablement states, including masked or socket-activated units. If running, use the discovered client socket with `ping` and `status` and capture the existing jails and SSH bans. Never start a service during discovery.
- Identify actual TCP listeners and local destination ports with `ss -ltnp` and correlate addresses, families and processes with the real SSH service invocation and effective `sshd -T` using its config and applicable context. For socket activation inspect effective Listen values, unit drop-ins and generated settings, and reconcile them with the running listeners, forwarding/NAT and network namespace. Noble can generate socket addresses from SSH configuration. Identify SSH authentication events and the observed client source addresses at the daemon.
- Inspect actual recent SSH auth records and rotation/read permissions. For journal logging, inspect record fields (for example with `journalctl -o verbose` using a discovered unit and bounded time window), the installed SSH filter and its local overrides. Confirm the service can read the relevant journal and has the systemd Python backend dependency. Match observed fields using the installed filter's effective `journalmatch`; in journal matching, a standalone plus separates alternative groups. For file logging, identify the actual readable file and confirm it receives fresh SSH failures. Review both positive and benign samples with the installed version's `fail2ban-regex` against the effective filter. Use the journal input mode for the journal if supported and ensure the same journal selection is exercised. Keep auth records and management IPs private.
- Identify the firewall that handles inbound SSH in the relevant namespace. Inspect applicable read-only ruleset/status commands for nftables, iptables including legacy versus nft compatibility and IPv6, UFW, or firewalld. Review installed action definitions and overrides, address families, chain/hook/priority and destination-port handling. Confirm the selected action can block SSH on every intended listener without widening the scope to other services. Account for upstream ACLs and proxies/shared source addresses. Stop planning application if the packet path or compatible action cannot be established.

## Plan and dry run

1. Record the approved scope, service impact, package/dependency changes if needed (including package scripts that may auto-start), exact config diff, client test commands, operator access and rollback steps. Identify and test a second access/recovery path such as an out-of-band console. Keep the existing session open. Confirm administrator source IPs or narrowly scoped CIDRs for IPv4 and IPv6 as applicable, including NAT/VPN and recovery paths. Preserve reviewed inherited exceptions, loopback policy and `ignoreself` behavior. An allowlist does not clear existing bans. Review overlapping jails and existing bans that might block those addresses.
2. Use a dedicated `jail.d/*.local` file scoped to `[sshd]`. Retain distro files and other jails. Inspect includes and lexicographic order within each group. Main jail precedence is `jail.conf`, `jail.d/*.conf`, `jail.local`, then `jail.d/*.local`. Look for duplicate protection under another jail, and inspect inherited settings, including explicit `action` values that could override or bypass `banaction`. Resolve conflicts in the reviewed plan before applying.
3. For journal-only logging choose `backend = systemd` and omit `logpath` from the override. Distro jail definitions may already contain a file path, so use the native dump to confirm the effective journal backend and that it adds journal matches with no file monitoring. If the shipped match is wrong, review a version-specific filter override or a compatible scoped filter customization and test the effective match. Avoid changing filter behavior for unrelated jails. For file logging choose an explicit file backend such as `polling` and set `logpath` to the discovered file. Review access, rotation and representative filter matches. Make TCP ports, retry threshold, find window and finite ban duration explicit.
4. Stage the complete trusted configuration tree and layout in a private scratch directory. Use the renderer there when its schema fits. With the matching native client, run `fail2ban-client -c "$STAGED_CONFIG" -t` and `fail2ban-client -c "$STAGED_CONFIG" -d`. Compare baseline and proposed dumps. Check diagnostics even on exit zero. Confirm SSH jail, filter, backend, log source, ports, allowlist and expanded actions and check for unexpected changes to other jails. Run native checks with only reviewed configuration and log inputs, under suitable access controls. If the package is missing, record the validation gap and use an isolated matching environment or defer. Dry run requires no package installation or service changes on the target. Parser and regex tests do not exercise runtime ingestion or kernel enforcement.

## Separately authorized application

Require explicit authorization for the exact host and reviewed operations, a working recovery path and the approved allowlist. Recheck listeners, package/config drift and recovery access. Back up affected config with ownership and modes and record any previously absent files, installed packages, active and enablement state, socket and service settings, existing jail/ban state and relevant firewall baseline. Protect backup contents and agree on a rollback cutoff. Leave SSH settings alone for this procedure.

If installation is separately approved, account for maintainer-script auto-start and package/activation rollback before installing. Keep activation gated until config validation succeeds. Install only the reviewed local override and any explicitly approved related changes, using atomic file replacement and preserving expected permissions. Test and dump the installed config with `fail2ban-client -c "$CONFIG_ROOT" -t` and `-d` again before any planned service change. Abort and restore on validation failure. Apply through the observed service manager or package-supported reload using the discovered socket/unit. Prefer a jail-scoped reload when supported and sufficient. Starting an inactive service or changing boot enablement requires corresponding authorization.

## Verification and rollback

- Use the correct socket with `fail2ban-client ping`, `status` and `status sshd`. Check `get sshd ignoreip`, `get sshd journalmatch` or `get sshd logpath`, and `get sshd actions`. For command actions inspect `get sshd action "$ACTION" actionban` and the applicable action properties and actual firewall rules. Confirm expected TCP ports, families and rule placement, fresh event ingestion and service/action logs. Some actions create rules only upon the first ban.
- Test continued access from the independent management path. A live enforcement test needs explicit approval and a dedicated, recoverable, non-management source. Never deliberately ban the current management IP or any shared administrator source. If approved, verify that representative failed logins reach the expected jail and trigger enforcement only on the intended ports/families, then remove the test ban with `fail2ban-client set sshd unbanip "$TEST_IP"` and confirm connectivity and rule cleanup. Report any live checks omitted.
- Roll back on degraded access, missed intended events, unexpected rules or action errors. Use the recovery path. If needed, check which jail owns a specific mistaken ban and perform targeted `set <JAIL> unbanip <IP>` against that jail. Restore prior file contents and metadata or remove the newly introduced override if absent before. Validate restored config before reloading or restarting as appropriate. Restore prior active/enablement state and any separately approved package changes under the plan. Check remaining bans and action-owned chains/sets, other jails and restored connectivity. Avoid flushing the firewall or clearing unrelated bans. Record any dynamic ban state that could not be restored.

## Offline renderer

Run `python3 scripts/render_sshd.py INPUT.json OUTPUT.local` as an unprivileged user in a private scratch directory. Use a dedicated staged output file. The renderer only parses JSON and writes text to the named output. It accepts exactly the following keys for journal mode (example data uses documentation addresses):

```json
{
  "ports": [2222, 2200],
  "allowlist": ["192.0.2.7", "2001:db8:5::/64"],
  "backend": "systemd",
  "banaction": "nftables-multiport",
  "maxretry": 5,
  "findtime": 600,
  "bantime": 900
}
```

For file mode use `"backend": "polling"` and add `"logpath"` with one literal absolute file path. Journal mode uses the effective SSH filter's match. Action names are syntactically checked. Choose one installed, reviewed multiport action and verify its expansion. The list of literal IP addresses and canonical CIDRs replaces the inherited jail allowlist, so include all approved inherited entries. Unsupported custom paths, DNS allowlist entries, filter expressions and action parameters need manual review and native testing. The helper does not inspect the host or establish that a jail can load or enforce bans. Offline checks cover serialization and rejected inputs. Native parser, journal/file integration and action enforcement require separate evidence.

## Primary references

- [Jammy jail manual](https://manpages.ubuntu.com/manpages/jammy/man5/jail.conf.5.html) and [Jammy client manual](https://manpages.ubuntu.com/manpages/jammy/man1/fail2ban-client.1.html)
- [Noble jail manual](https://manpages.ubuntu.com/manpages/noble/man5/jail.conf.5.html) and [Noble client manual](https://manpages.ubuntu.com/manpages/noble/man1/fail2ban-client.1.html)
- [Upstream 1.0.2 jail defaults](https://github.com/fail2ban/fail2ban/blob/1.0.2/config/jail.conf) and [upstream SSH filter](https://github.com/fail2ban/fail2ban/blob/1.0.2/config/filter.d/sshd.conf)
- [Ubuntu OpenSSH socket activation notes](https://discourse.ubuntu.com/t/sshd-now-uses-socket-based-activation-ubuntu-22-10-and-later/30189)
