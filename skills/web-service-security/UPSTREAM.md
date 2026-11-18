# Upstream provenance

This skill contains modified and adapted guidance from the Cloudflare Skills project (cloudflare/skills), pinned to commit `5108325ecceabc899c761e07aa617b09c02445ee`, distributed under Apache License 2.0. The upstream [LICENSE](https://github.com/cloudflare/skills/blob/5108325ecceabc899c761e07aa617b09c02445ee/LICENSE) is reproduced unchanged in this package. The pinned tree contains no NOTICE file.

- [skills/workers-best-practices/references/runtime-patterns.md](https://github.com/cloudflare/skills/blob/5108325ecceabc899c761e07aa617b09c02445ee/skills/workers-best-practices/references/runtime-patterns.md) supplies bounded streaming, cryptographic randomness, secure comparison and fail-closed errors.
- [skills/workers-best-practices/references/configuration.md](https://github.com/cloudflare/skills/blob/5108325ecceabc899c761e07aa617b09c02445ee/skills/workers-best-practices/references/configuration.md) supplies secret storage, ordinary configuration and diagnostic hygiene.
- [skills/cloudflare-one/SKILL.md](https://github.com/cloudflare/skills/blob/5108325ecceabc899c761e07aa617b09c02445ee/skills/cloudflare-one/SKILL.md) supplies credential destination checks, positive and negative tests, staged rollout and rollback.
- [skills/sandbox-stable/SKILL.md](https://github.com/cloudflare/skills/blob/5108325ecceabc899c761e07aa617b09c02445ee/skills/sandbox-stable/SKILL.md) supplies separation of untrusted execution and credential-bearing controls.

The instructions were rewritten for provider-neutral generated web services and integrations. The adaptation omits Cloudflare product setup, platform limits and vendor-specific APIs. The offline helper and fixtures were authored for this package.
