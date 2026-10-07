# Codex Workflow Plugin

Experimental Codex plugin for coordinating a user-approved workflow across Codex, Claude, and Grok through Pi without manually copying prompts between terminal tabs.

## Status

**Alpha 0.1.0.** This release packages a self-contained orchestration skill for clean-session testing. It does not include the large synthetic pilot, a generic job manager, hooks, or MCP servers. Its Grok write confinement is currently macOS-only because it uses `sandbox-exec`; unsupported platforms fail closed.

The first real brainstorm exposed that Claude CLI advisory calls could inherit plugins, MCP tools, skills, plan behavior, and a large ambient system context even when built-in tools were disabled. Fable then used plugin tools and attempted a plan write. The plugin now routes both Fable 5 and Opus 5 advisory calls through a deterministic Pi runner. It requires Anthropic OAuth, disables all tools and ambient Pi resources, records per-attempt evidence, emits bounded progress, and requires Pi's native terminal sequence rather than trusting a bare exit code. The workflow retains `interrupted_unknown` handling without blind retry.

Codex owns the user conversation, decisions, planning, review, and acceptance. Claude Fable or Opus advise through Pi only when their specialties are useful. Their runner is tool-free: Codex supplies current sources and relevant repository evidence in a compact context pack. Grok through Pi may implement only explicitly bounded work. The bundled writer runner locks `xai/grok-4.5`, removes shell access, confines writes to exact paths on macOS, routes OAuth without recording the bearer, and preserves sanitized evidence outside the target repository. The skill never silently falls back to Claude CLI, Grok Build, or another billing path.

Commits remain user-gated. After the user explicitly asks to commit, Codex may send only the staged diff and bounded task facts to a tool-free `openai-codex/gpt-5.4-mini` commit scribe, validate its message, commit without model attribution, and then produce a verified continuation prompt for a new Codex task. The scribe never receives Git or source-write authority.

## Install from GitHub

```bash
codex plugin marketplace add thanhan92-f1/codex-workflow-plugin
codex plugin add codex-workflow-plugin@personal
```

Start a new Codex task after installation so the skill is picked up. Invoke it explicitly for the first pilot:

> Use the workflow orchestrator for this task.

## Update an existing install

Refresh the configured Git marketplace before reinstalling; `plugin add` alone installs from the current local marketplace snapshot and may therefore reuse an older version:

```bash
codex plugin marketplace upgrade personal
codex plugin add codex-workflow-plugin@personal
```

Then start a new Codex task so it loads the updated skill and bundled runner.

## What to test

Use the first small, real bug, feature, review, or project-start decision that naturally occurs. Do not manufacture another synthetic implementation merely to produce a green result. After the task, evaluate its transcript, actual Git diff, independent checks, browser evidence where relevant, and the user's required interventions.

The installed skill describes cross-task evaluation, transactional review boundaries, commit authorization, and continuation evidence. One task proves feasibility, not productivity savings.

## Privacy and authority

The plugin contains no credentials, telemetry, MCP connection, or captured pilot logs. Installation and provider authentication do not authorize source edits. Target-repository instructions and task-specific user approval remain authoritative.

## Development history

The large fixture suite, raw provider traces, phase plans, and implementation reports remain in a separate local development workspace and are intentionally excluded from this public release.
