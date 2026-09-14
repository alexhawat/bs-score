# Security Policy

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately via [GitHub Security Advisories](https://github.com/alexhawat/bs-score/security/advisories/new).
You will receive an acknowledgement as soon as possible.

## Security response

When a private advisory is opened, the maintainer follows this process:

1. **Acknowledge** the reporter (aim for two business days).
2. **Triage** severity and affected versions; confirm a reproduction privately.
3. **Patch** on a private fork or embargoed branch; do not discuss the
   vulnerability in a public issue until disclosure.
4. **Release** a fix on `main` and credit the reporter unless they ask
   otherwise.
5. **Disclose** on the agreed date (coordinated disclosure).

## Coordinated vulnerability disclosure

After a fix is available (or the reporter and maintainer agree no fix is
required):

- Publish a GitHub Security Advisory with affected versions and the patched
  release.
- Give reporters a reasonable window to confirm the fix before the advisory
  goes public.
- Do not require public proof-of-concept before acknowledgement.

## Supported Versions

Only the latest `main` is supported with security updates.
