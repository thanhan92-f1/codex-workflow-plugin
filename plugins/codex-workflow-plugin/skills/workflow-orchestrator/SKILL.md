---
name: workflow-orchestrator
description: Coordinate a user-approved coding workflow in which Codex owns the conversation, decisions, planning, review, and acceptance; Claude Fable or Opus advises through Pi when useful; and Grok through Pi implements bounded source changes. Use only when the user asks to use this workflow, delegate to these specialists, or resume a task already using it.
---

# Workflow orchestrator

Codex remains the primary agent and final synthesizer. This alpha is a **skill**, not a background service, generic job manager, filesystem sandbox, or blanket authorization to call providers or edit repositories.

## Start with the actual task

Read the target repository instructions and live state. Classify the requested outcome: answer, exploration, experiment, review, bug fix, feature, or project start. Use specifications and plans in proportion to the work; do not force a simple question or local fix through a feature pipeline.

Keep user-confirmed decisions ahead of model recommendations. Before consulting or delegating, prepare one compact context pack containing:

- the exact question or outcome;
- relevant files and symbols only;
- locked decisions, constraints, invariants, and prohibited approaches;
- what has already been tested or observed;
- exact writable ownership, if any;
- acceptance criteria independent of the worker's answer;
- uncertainties and required output format.

Never include secrets, credentials, unrelated user data, or the entire conversation when a small pack is sufficient.

## Choose specialists deliberately

- Use Claude Fable for architecture, cross-domain design, technical research, non-obvious approaches, or challenging a structural assumption.
- Use Claude Opus for UI/UX, journeys, roles, permissions, and human-facing trade-offs.
- Use Grok through Pi for explicitly delegated implementation or broad codebase scanning when it materially helps.
- Use none when Codex can answer or verify the work directly.

Before the first call in a task, after an upgrade, or after a failed command, inspect the locally installed CLI help. Never invent flags, models, permission modes, or output formats from this skill. Keep specialists read-only unless the user and repository scope authorize a specific write.

Before launching an external specialist, read [specialist observability](references/specialist-observability.md). For Fable or Opus advisory calls, use the bundled `scripts/run_pi_advisor.py` runner instead of reconstructing a Pi or Claude command from prose. It requires Anthropic OAuth, selects the locked Fable 5 or Opus 5 model, disables tools and every ambient Pi resource, creates invocation-owned evidence, and refuses to report success without Pi's native terminal sequence. Never fall back to Claude CLI or an API-key billing path. A blocking print command that emits nothing until the final answer is poor evidence for a long-running call. Yield control promptly and keep the user informed without treating silence alone as failure.

The advisory runner is intentionally tool-free. Codex gathers current primary-source research and relevant repository evidence, then supplies a compact context pack. Do not treat model memory as current evidence. If an advisory task cannot be answered without independent browsing or broad repository exploration, surface that need and let Codex collect the evidence; do not silently widen the runner's tool access.

For this alpha, the selected implementation route is Pi with `xai/grok-4.5` and thinking `high`. Advisory and implementation calls have different authority and must not share a generic writer. Do not silently substitute a different model, use Grok Build or Claude CLI, switch to an API-key billing path, or retry through another provider. Confirm the installed Pi model identifier and syntax before launch.

## Delegate and review

For a write task, name one writer, exact files, allowed operations, commands it may run, and the next review checkpoint. Include scratch paths in ownership; omit shell access when native file tools suffice. Do not allow overlapping writers.

Before delegating writes, read [Pi implementation runner](references/implementation-runner.md) and use the bundled exact-file macOS runner. Do not reconstruct Pi authentication, sandbox profiles, or scratch paths in the target task. If its platform or write-boundary preflight fails, keep the specialist read-only and surface the gate instead of launching an unrestricted writer.

Treat provider exit, delivered work, test evidence, and user acceptance as separate facts. Exit zero or a worker saying “fixed” is only a claim. Codex reviews the actual diff and runs checks chosen from the requirement and codebase. Use browser testing for relevant UI behavior, not as a replacement for other evidence.

For stateful or undoable behavior, read [review gates](references/review-gates.md). Test meaningful boundaries with the ordinary behavior before and after the changed operation; do not accept same-kind happy-path sequences as proof of isolation.

Keep finding IDs across repair. A repair claim moves a finding to awaiting recheck; close it only after current independent evidence passes. Consolidate visible findings into one bounded repair packet rather than sending repeated fragments.

Never automatically retry a call whose completion is unknown. Do not infer that an old PID is live, restart a stored command, or mutate another invocation's artifacts. Preserve raw provider output when practical and report uncertainty honestly.

## Handoff and evaluation

At a meaningful checkpoint, keep a compact durable handoff in the task or an existing project record: requested outcome, approved scope, source identity, specialist/model used, result, evidence, open findings, user interventions, and next safe action. Do not create a database, daemon, or large transcript archive just to satisfy this guidance.

Never commit from a worker completion or green check alone. When the user explicitly asks to commit, read [commit gate and continuation packet](references/commit-and-continuation.md). Preserve the no-automatic-commit rule, use the tool-free commit scribe only on the exact staged diff, and emit a verified continuation prompt after a successful commit.

To evaluate a run from another Codex task, use [evaluation guidance](references/evaluation.md). A thread transcript is coordination evidence, not correctness evidence.

## Alpha limits

Version 0.1 has observed evidence for clean-session skill pickup, isolated Pi advisory, one real bounded Grok implementation with Codex repair, a tool-free commit-scribe smoke, and exact-file macOS sandbox enforcement. It does not yet prove automatic activation, compaction recovery, live worker cancel/resume, cross-platform write confinement, or reduced cost and user effort across repeated tasks. Do not convert an earlier task's approvals into authority for a new repository.
