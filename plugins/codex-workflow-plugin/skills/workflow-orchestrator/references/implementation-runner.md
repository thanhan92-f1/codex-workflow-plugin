# Pi implementation runner

Read this reference before delegating source writes to Grok.

Use the bundled `scripts/run_pi_writer.py` instead of reconstructing Pi, OAuth, scratch, or sandbox commands in the task. The runner is intentionally macOS-only in this alpha because it requires `sandbox-exec`. It fails closed on other platforms.

The runner locks:

- provider/model: `xai/grok-4.5` with thinking `high`;
- authentication: existing xAI OAuth, passed to the child without recording the bearer;
- ambient context: no sessions, extensions, skills, prompt templates, themes, or repository context files;
- tools: read/search plus edit/write, with no shell;
- source authority: exact `--write-file` paths under one repository root;
- evidence: receipt, raw JSONL, stderr, terminal result, and sandbox profile under the caller-supplied durable evidence root;
- Git safety: `.git` is outside the write allowlist, so the worker cannot commit or push.

Codex must prepare the task pack before invoking the runner. Include exact writable paths, intended behavior, acceptance criteria, locked decisions, prohibited changes, relevant files/symbols, and checks Codex will run later. `--write-file` authorizes creation when a named file does not yet exist; the runner records any placeholders it creates.

Do not put the evidence root or invocation scratch inside the target repository. A recommended path is `~/.codex/workflow-evidence/<repo>/<task>/grok-writer`. Keep sanitized receipts and provider output after source scratch cleanup so another task can evaluate the run.

The runner does not execute tests. This is deliberate: shell command allowlists are not enforced by Pi's generic bash tool, while filesystem confinement is. Codex runs repository tests and browser checks independently after the worker exits.

Runner completion proves only that Pi delivered a terminal Grok response. Codex still reviews every changed path, detects writes outside the expected Git diff, runs independent checks, and maintains finding IDs through repair and recheck.

If preflight fails, fix only the reported local route and launch a fresh attempt ID. If completion is unknown or interrupted, do not retry automatically. Never reconstruct the older bearer-in-argv flow or use a repository-local Pi config directory.
