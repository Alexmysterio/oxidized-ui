# Security policy

## Supported versions

Security fixes are applied to the latest `main` branch and the most recent
release image built from it. Older images are not supported.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Use GitHub's private vulnerability reporting:

1. Open the repository on GitHub.
2. Select **Security**.
3. Select **Report a vulnerability**.

Include:

- affected version or commit;
- deployment mode (single container or four-container);
- steps to reproduce;
- impact;
- any proposed fix.

Do not include real credentials, private keys, tokens, or production data.

## Scope

In scope:

- authentication, sessions, MFA, API tokens, and OIDC;
- authorization and role boundaries;
- CSRF, origin handling, and proxy-header trust;
- credential storage and encrypted export;
- command execution and file access;
- Docker configuration and the Caddy boundary;
- dependency and image vulnerabilities.

Out of scope:

- attacks that require an already-compromised host or root container access;
- denial of service by an authenticated administrator;
- misconfigured DNS, firewalls, or reverse proxies outside this project;
- vulnerabilities in third-party devices backed up by Oxidized.

## Secure deployment checklist

- Use HTTPS only.
- Import the private CA into client trust stores.
- Keep `SESSION_COOKIE_SECURE=true`.
- Set `TRUST_PROXY_HEADERS=true` only when Caddy is the direct proxy.
- Keep the UI on a trusted network or VPN.
- Use a unique administrator password and enable MFA.
- Treat API tokens as passwords.
- Set `METRICS_TOKEN` if metrics are reachable by untrusted clients.
- Back up `.env` and `data/` securely; the Fernet key is required to decrypt
  credentials.
- Prefer the four-container mode when stronger process isolation is required.

## Known residual risks

- The single-container mode runs `supervisord` and Caddy as root. The UI and
  Oxidized run as UID/GID 30000, but they share the container. Use
  `docker-compose.secure.yml` for stronger isolation.
- The supervisor RPC listens only on `127.0.0.1` inside the container and has no
  separate authentication. Any process already inside the container can use it.
- OIDC uses authorization code + PKCE and the provider `userinfo` endpoint. It
  does not validate an ID token signature or apply local MFA to OIDC users.
- Metrics are unauthenticated when `METRICS_TOKEN` is empty. Restrict network
  access or set a token.
- Trivy findings are reported in CI; the workflow does not fail the build on
  every unfixed base-image CVE.

See [Security audit](docs/SECURITY-AUDIT.md) for the latest review.
