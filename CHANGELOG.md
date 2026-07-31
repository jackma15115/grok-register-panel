# Changelog

## Unreleased

- Add private imported-account management with password login, SSO extraction, optional CPA/Grok2API conversion, concurrent Docker/Xvfb workers, task controls, and secret-free API views.
- Add a Docker-first deployment with baked Camoufox, Xvfb/browser dependencies, Compose health checks, strong panel authentication, unified `/data` persistence, and automated GHCR publishing.
- Add TI Temp Mail with optional create-token authentication, main/subdomain modes, domain-pool rotation, connectivity checks, and redacted mailbox activity in the panel.
- Add authenticated exports for SSO-only text and `email,passwd` CSV account data, including pending SSO records while excluding risk-rejected records.
- Treat batch counts as successful-account targets so failed attempts no longer consume a requested slot.
- Supervise headless batches and automatically resume remaining task slots after a Playwright/Camoufox driver crash or stall.
- Persist batch slot progress atomically so completed accounts are not repeated during recovery.

## 0.2.0 - 2026-07-30

- Redesign the live panel with responsive light and dark themes.
- Add a dedicated usage and troubleshooting view.
- Add pending SSO and account-file recovery with success dequeue.
- Move learned ASN rules from Python source into locked JSON state.
- Scope process discovery and termination to one project root.
- Require monitor authentication for operational read and write APIs.
- Add security headers, bounded request bodies, and redacted log output.
- Create runtime credentials, account data, logs, state, and PID files owner-only.
- Add release tests, CI, a systemd service template, and deployment checks.
