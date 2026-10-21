# Changelog

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
