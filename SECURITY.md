# Security Policy

This repository distributes a Claude Code plugin. Its components may influence agent behavior, invoke local commands, interact with files, or start external tools. Review plugin updates and executable components before enabling them in a sensitive environment.

## Supported Versions

Security fixes target the latest published release and the `main` branch. Older releases are not guaranteed to receive backports. If you discover an issue in an older release, report it with the affected version so maintainers can assess its impact.

## Reporting a Vulnerability

**Report security vulnerabilities privately. Do not include exploit details, credentials, or sensitive files in a public issue or pull request.**

1. Open the repository's **Security** tab and select **Report a vulnerability**, if private vulnerability reporting is enabled.
2. Describe the affected release or commit, impacted plugin component, prerequisites, reproducible steps, and potential impact. Include a minimal proof of concept when appropriate, with all secrets removed.
3. If private reporting is unavailable, open a public issue **requesting a private security contact channel only**. Do not disclose vulnerability details in that issue.

Maintainers will assess reports, coordinate remediation, and determine whether a GitHub Security Advisory or release notice is appropriate. Response and remediation timing depend on severity, reproducibility, and maintainer availability; no fixed service-level agreement is implied.

## Security-Relevant Components

Reports are especially useful for vulnerabilities involving:

- **Hooks and executables:** unsafe subprocess execution, command injection, unexpected side effects, or access outside intended paths.
- **Skills, commands, agents, and workflows:** instructions that induce unsafe tool use, disclose sensitive data, or bypass expected user approval.
- **MCP and LSP integrations:** untrusted server execution, excessive privileges, insecure communication, or improper handling of credentials.
- **Plugin manifests and configuration:** unsafe defaults, path traversal, unintended component loading, or insecure environment-variable handling.
- **Dependencies and releases:** compromised packages, vulnerable transitive dependencies, artifact tampering, or weaknesses in CI/release automation.

## Automated Security Checks

The repository uses **PySentry** to audit Python dependency metadata and resolved dependencies. Scanner policy, including failure thresholds and advisory sources, is configured in `pyproject.toml`; the scanner is installed through uv's `security` dependency group.

- **CI:** The reusable `.github/workflows/supply-chain.yml` workflow checks dependencies. Successful audit results may be reused using a cache keyed to dependency metadata and an ISO-week window.
- **Scheduled audit:** `.github/workflows/weekly-security.yml` runs weekly and forces a fresh scan, independently of dependency changes. It can also be started manually.
- **Findings:** SARIF reports are submitted to GitHub Code Scanning where repository permissions and features allow it. Scheduled runs also retain a report artifact when one is produced.
- **Failure tracking:** A failing scheduled audit creates or updates a GitHub issue containing an audit summary and available findings. A later successful audit closes the outstanding tracking issue.

An audit can fail for reasons other than a known vulnerability, including scanner or infrastructure errors. A missing SARIF report does not mean that the repository passed its security checks.

### Limitations

These checks identify issues covered by their advisory sources and configured policies. They do **not** establish that the plugin, its dependencies, or its releases are free of malicious behavior. In particular, dependency auditing does not comprehensively detect prompt injection, unsafe agent instructions, malicious hooks, compromised MCP servers, secret exfiltration, or previously undisclosed vulnerabilities.

Automated tracking issues are **not a private disclosure channel**. If a finding involves an unreported exploitable weakness or sensitive data, disclose it privately rather than posting additional details to a public issue.

## Guidance for Users

- Install updates from trusted repository releases and review changes to hooks, scripts, executables, and external-tool configuration.
- Run the plugin with the least privileges necessary. Avoid giving agent processes broad access to credentials, production infrastructure, or unrelated files.
- Review requests to execute commands or connect to MCP/LSP servers, especially when they originate from untrusted content.
- Keep dependencies and the plugin current, and investigate security advisories relevant to the installed version.

Security tooling reduces exposure; it does not replace review of executable plugin behavior and the permissions granted to it.
