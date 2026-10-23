# Security and error audit

Date: 2026-10-23
Scope: application code, authentication flows, Docker/Caddy configuration,
frontend, dependency checks, and CI.

## Summary

No critical authentication bypass or remote code execution issue was found in
the reviewed paths. Five hardening fixes were applied:

| Severity | Finding | Status |
|---|---|---|
| High | SSH test auto-trusted unknown host keys | Fixed |
| High | Proxy forwarded headers could be spoofed | Fixed |
| Medium | Login could redirect to an attacker-controlled path | Fixed |
| Medium | OIDC state store was unbounded and provider errors leaked as 500s | Fixed |
| Medium | Database and config files were group/world-readable | Fixed |

Residual risks are documented in [SECURITY.md](../SECURITY.md).

## Fixed findings

### 1. SSH test accepted unknown host keys

`backend/app/node_test_service.py` used `paramiko.AutoAddPolicy()` while sending
the configured username and password. A network attacker could present a new SSH
host key and receive credentials during **Test connection**.

Fix:

- load the same `known_hosts` used by Oxidized;
- use `paramiko.RejectPolicy()`;
- report `host_key_unknown` and require the explicit **Trust host key** action.

### 2. Spoofable forwarded headers

The UI trusts `X-Forwarded-For` when `TRUST_PROXY_HEADERS=true`. Caddy previously
forwarded a client-supplied header, so an attacker could put an allowlisted IP
first and bypass the IP allowlist.

Fix: Caddy now overwrites `X-Forwarded-For`, `X-Forwarded-Host`, and
`X-Real-IP` with values derived from the actual connection:

```caddyfile
reverse_proxy 127.0.0.1:8080 {
    header_up X-Forwarded-For {remote_host}
    header_up X-Forwarded-Host {host}
    header_up X-Real-IP {remote_host}
}
```

The same change was applied to the four-container Caddyfile.

### 3. Open redirect after login

`login-page.tsx` used `location.state.from` directly. The value is normally set by
the protected-route guard, but it was not validated.

Fix: only accept targets beginning with `/` and reject `//` prefixes.

### 4. OIDC state and error handling

The in-memory state map had no expiry cleanup or size cap. Provider/network
errors could produce an unhandled 500.

Fix:

- expire states after 10 minutes;
- cap the map at 1,000 entries;
- return a generic login redirect on provider/network failure;
- keep detailed errors out of the HTTP response.

### 5. Data permissions

The SQLite database and Oxidized config were created with mode `0644`.

Fix:

- the container entrypoint applies `chmod -R go-rwx` to `/data` and
  `/oxidized-config`;
- the database and config are now `0600`, owned by UID/GID 30000;
- `/var/log/supervisor` remains traversable by the UI process, while logs are
  owned by the supervisor.

Existing installations should apply the same permissions once:

```bash
docker exec -u 0 oxidized-ui chmod -R go-rwx /data /oxidized-config
```

## Reviewed and accepted

- **Internal source endpoint:** requires `X-Oxidized-Source-Token` and uses a
  constant-time comparison.
- **CSRF:** HMAC token bound to the opaque session; unsafe requests require both
  Origin/Referer and the header. Bearer tokens bypass CSRF because they are not
  cookie-based.
- **SSH host-key trust:** `ssh-keyscan` receives a validated IP/hostname and an
  integer port; it does not use a shell.
- **Oxidized URLs:** node and group names are URL-quoted before being sent to
  Oxidized.
- **CSV export:** formula-leading cells are prefixed to prevent spreadsheet
  injection.
- **Encrypted export:** AES-256-GCM with PBKDF2-SHA256 (600,000 iterations);
  passphrase is not stored or audited.
- **OIDC user mapping:** new users are derived from the subject hash, not from an
  unverified email or username.
- **Single-container mode:** no Docker socket is mounted. Caddy is the only
  published process.
- **Headers:** CSP, HSTS, `X-Frame-Options`, `nosniff`, referrer policy, and no
  `Server` header.

## Residual risks

- `supervisord` XML-RPC is unauthenticated on container loopback. It is not
  reachable from the host or network, but any process already in the container
  can use it.
- OIDC does not validate an ID token; it uses the provider `userinfo` endpoint
  over TLS. OIDC users do not go through local MFA.
- `METRICS_TOKEN` is optional. Set it if `/api/metrics` is reachable by clients
  that should not see node names and backup status.
- The single-container mode runs root processes (`supervisord`, Caddy). The
  four-container mode is available for stronger isolation.
- Trivy reports unfixed base-image CVEs without failing the build. Review the CI
  report before each production release.
- OIDC has not been tested against every provider.

## Error review

- Backend tests and Ruff pass.
- Frontend tests, typecheck, i18n, and build pass.
- Playwright login smoke and real Oxidized contract tests pass in CI.
- Python `bandit` remaining findings are false positives or documented residual
  risks (XML-RPC to localhost, subprocess with a fixed binary, managed
  `0.0.0.0` Oxidized API listen inside the container).
- No unhandled error that exposes credentials or stack traces was found in the
  reviewed request paths.
