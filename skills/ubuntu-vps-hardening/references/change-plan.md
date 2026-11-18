# Synthetic change-plan schema

Run `python3 scripts/check_change_plan.py plan.json` with a synthetic UTF-8 JSON file up to 16 KiB. Supply exactly these keys.

- `actions` is an array of distinct strings from `disable_root_ssh`, `disable_password_ssh`, `restrict_ssh_path`, and `operator_core_change`.
- `affected_families` is an array of distinct `ipv4` and/or `ipv6` for path restrictions. Use an empty array when there is no path restriction. An empty array with a restriction leaves the scope unknown and blocks review.
- `evidence` is an object using only the keys below. Values are true for verified prerequisites, false for failed ones, and null or omitted for unknown. Use synthetic values and include no credentials or machine output.

| Action | Evidence required |
| --- | --- |
| disable_root_ssh | alternate_admin_fresh_independent_key_login, alternate_admin_sudo_verified, provider_console_recovery_verified, management_session_retained |
| disable_password_ssh | affected_accounts_key_logins_verified |
| restrict_ssh_path | effective_listener_verified, recoverable_rollback, and ipv4_replacement_tested and/or ipv6_replacement_tested for each affected family |
| operator_core_change | Routes the entire plan to external maintenance. Submit a separate plan for independent in-scope actions. |

```json
{"actions":["disable_password_ssh"],"affected_families":[],"evidence":{"affected_accounts_key_logins_verified":true}}
```

```json
{"actions":["restrict_ssh_path"],"affected_families":["ipv4","ipv6"],"evidence":{"effective_listener_verified":true,"recoverable_rollback":true,"ipv4_replacement_tested":true}}
```

The first case prints `reviewable prerequisites_reported`. The second prints `blocked ipv6_replacement_tested`. Output uses fixed reason codes. Treat only reviewable as a completed prerequisite review. `reviewable no_changes_requested` establishes no security properties. This offline aid checks supplied evidence flags only. Authorization, running configuration, actual access and compliance require independent evaluation.
