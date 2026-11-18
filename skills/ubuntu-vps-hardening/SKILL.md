---
name: ubuntu-vps-hardening
description: Review Ubuntu 24.04 VPS security or plan and verify scoped hardening when the task requests it.
---

Use for a requested Ubuntu VPS security assessment or scoped hardening change. Discovery, validation and activation are inert. Follow the task's existing authorization and actual worker privileges. A review authorizes the requested evidence collection only. Apply changes only within the scope of an authorized change task and reuse approval already given for routine steps.

1. Read [the audit and change workflow](references/workflow.md). Record evidence, timestamp, vantage point and uncertainty. Check the observed topology against supplied context.
2. Plan the narrowest useful change with prerequisites, impact, verification and recovery. Use [the synthetic plan helper](references/change-plan.md) to review management-access prerequisites offline.
3. Apply and verify authorized changes in recoverable steps. Use the existing ubuntu-fail2ban skill for bans. Route operator-owned source, build, dependencies, .env, startup and update findings to external owner maintenance.
