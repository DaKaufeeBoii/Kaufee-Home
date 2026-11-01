# Changelog

## 0.5.0

- Add Session-Level Scoped Grants (`src/kaufee/safety/grants.py`) with `--grant-workspace <duration>` support (e.g. `15m`, `1h`) to bypass repetitive confirmation prompts while preserving safety gates for destructive operations.
- Add Desktop System Automation Tools (`src/kaufee/tools/system.py`):
  - `launch_application`: Launches verified desktop programs (Notepad, Calculator, VS Code, Explorer) with strict system binary allowlisting and safety checks.
  - `list_system_processes`: Queries running processes, PIDs, memory usage, and CPU percentages via `psutil`.
  - `send_desktop_notification`: Sends non-intrusive desktop toast notifications across Windows, macOS, and Linux.
- Add Clipboard Automation Tools (`src/kaufee/tools/clipboard.py`):
  - `read_clipboard`: Reads system clipboard text with automated credential and sensitive data redaction.
  - `write_clipboard`: Safely copies text content to the system clipboard.
- Extend Browser Automation (`src/kaufee/tools/browser.py`):
  - Added `browser_click` and `browser_fill` for interactive UI element clicks and form filling.
- Add Standalone Local Web Browser Dashboard (`kaufee web` and `kaufee ui`) powered by zero-dependency HTTP server and REST APIs.
- Add `psutil` and `pyperclip` dependencies to `pyproject.toml`.

## 0.4.0

- Add Model Context Protocol (MCP) client and manager (`src/kaufee/mcp/`) enabling stdio JSON-RPC tool connections from `.kaufee/mcp_servers.json`.
- Implement Pluggable Execution Runners (`src/kaufee/tools/runner_base.py`) supporting `SubprocessRunner` and resource-bounded, network-isolated `DockerRunner` (`--network none`, 512MB RAM, 1.0 CPU limit).
- Add Two-Tier Hybrid Cascading LLM Router (`src/kaufee/llm/router.py`) providing local-first generation ($0 cost) with automatic escalation to frontier cloud APIs on local failure or repair directives.
- Update `PolicyEngine` to enforce path safety and autonomy approvals across external MCP tools.

## 0.3.0

- Add browser automation tools: `browser_open`, `browser_scrape`, and `browser_download` supporting Playwright headless automation and an HTTP fallback.
- Introduce pre-flight plan approvals (`--approval-mode plan` by default) to eliminate alert fatigue by presenting the full task plan upfront for one-click authorization.
- Add in-terminal interactive TUI dashboard (`kaufee dashboard` and `kaufee tui`) built with Textual for live audit log inspection, event streams, and Responsible AI principle telemetry.
- Add `textual` and `playwright` dependencies to `pyproject.toml`.

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
