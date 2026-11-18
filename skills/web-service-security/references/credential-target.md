# Offline credential target review

Run `python3 scripts/check_credential_target.py input.json` on synthetic UTF-8 JSON (up to 16 KiB), with exactly these fields.

```json
{"intended_origin":"HTTPS://API.example.test:443","request_url":"https://api.example.test/items","redirects":["https://api.example.test/next?cursor=2"]}
```

Use an independently configured intended HTTPS origin with only an authority and optional root slash. Supply an absolute request URL and an ordered array of absolute proposed redirect URLs, possibly empty. Supply no credentials, including query tokens. Resolve relative Location values with the actual HTTP client before reviewing a hop. The helper accepts ASCII DNS hostnames, canonical dotted IPv4 and bracketed IPv6. Scheme and DNS hostname case are normalized, IP addresses use their canonical form, and omitted HTTPS port means 443. The grammar rejects fragments, userinfo, Unicode, whitespace/control characters, backslashes, ambiguous authority and leading double-slash paths, alternate numeric IPv4 forms, trailing DNS dots, malformed escapes and invalid ports. Use ASCII A-labels for internationalized hostnames only after conversion by the client.

The example reports `reviewable same_https_origin`. Results use fixed codes and do not echo URLs. Configure the HTTP client with automatic redirects disabled and review the initial destination and each resolved hop before attaching credentials. Stop on a blocked result. This helper reads the specified file and performs no writes, DNS lookups, network calls or redirect following. The result describes the supplied destinations only. Destination authorization, DNS/SSRF safeguards and actual client behavior require independent verification.
