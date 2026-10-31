# Changelog

## 0.2.5

- Implement end-to-end Responsible AI architecture mapping to the 6 core principles: Fairness, Reliability & Safety, Privacy & Security, Inclusiveness, Transparency, and Accountability.
- Add `kaufee principles` CLI command to display the Responsible AI principle matrix and runtime mitigations.
- Introduce tiered Autonomy Modes (`--mode manual`, `assisted`, `autonomous`) enforcing granular human oversight.
- Add `SensitiveDataRedactor` to sanitize passwords, tokens, API keys, private keys, and PII in audit logs and console outputs.
- Add `PromptInjectionGuard` detecting and intercepting direct and indirect instruction overrides and jailbreaks.
- Add `AgentCircuitBreaker` detecting repetitive loops and cascading tool failures to prevent runaway execution.
- Tag all policy decisions and audit records with their governing Responsible AI principles.
- Update benchmark workspace isolation to prevent collision with application security path filters.

## 0.2.4

- Ignore local `.env` files so API credentials are not accidentally added to Git; continue tracking `.env.example`.
- Rewrite `guide.md` as copy-and-paste installation and usage steps for desktop, Chromebook, Android, and SSH-based mobile use.

## 0.2.3

- Normalize Windows and POSIX path separators before safety checks so traversal and protected-file checks behave consistently across operating systems.
- Add regression coverage for Windows-style traversal and protected paths on every CI platform.
- Create the gitignored pytest output directory in CI before writing JUnit results on a clean runner.

## 0.2.2

- Require explicit user approval before executing generated Python by default.
- Removed verifier-side script execution that could bypass the Python runner's approval and limits.
- Bound configuration for captured process output to at most 1 MB.
- Restrict CI token permissions, pin CI actions to immutable revisions, and publish pytest failures in the job summary.

## 0.2.1

- Restore directories through a staged replacement, preserving the current directory if restoration fails.
- Restore overwritten move destinations with an atomic copy after validating the backup.
- Bound captured Python stdout and stderr while continuing to drain child-process pipes.
- Enforce `read_file` limits in bytes and report truncation in tool metadata.
- Add regression coverage for restore failures, bounded output, and UTF-8 byte limits.

## 0.2.0

- Added safer workspace operations, undo backups, bounded Python execution, cross-device usage guidance, and CI coverage.
