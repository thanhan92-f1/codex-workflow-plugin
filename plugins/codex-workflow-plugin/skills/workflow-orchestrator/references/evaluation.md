# Evaluate a workflow run

Evaluate three separate questions:

1. **Coordination:** Did Codex retain locked decisions, choose specialists deliberately, send bounded context, avoid duplicate/unknown retries, and preserve findings through recheck?
2. **Correctness:** Does the actual diff satisfy the requirement, repository instructions, tests, and relevant browser behavior? A task transcript or worker report cannot establish this alone.
3. **Usefulness:** How many prompt transfers, repeated-decision reminders, manual handoff rescues, permission/product decisions, and repair rounds did the user experience? Separate legitimate decisions from orchestration failures.

## Minimum evidence

- Codex task/thread identity and plugin version.
- Target repository plus source revision before and after.
- Requested outcome, locked decisions, authorized files/operations, and acceptance criteria.
- Specialists actually called, selected provider/model, and observed completion state.
- Actual changed-file list and diff.
- Independent checks and browser evidence where relevant.
- Open/closed findings with current recheck evidence.
- Observed user interventions and wall time when available; unknown values remain unknown.
- Provider-reported token usage or cost when present; do not infer missing subscription accounting from public API prices.
- For committed work: staged-diff digest, resulting commit identity, remaining worktree, and the continuation packet supplied to the next task.

## Cross-task review

When Codex app task tools are available, the evaluator may locate and read the other task's recent status and messages. Identify the task explicitly to avoid reviewing the wrong thread. If the implementation lives in another worktree or host, obtain an accessible Git ref, diff, or handoff before judging code.

Do not treat a transcript summary, provider exit zero, green worker-authored tests, or a commit message as independent acceptance. Review the live diff and rerun proportionate checks. Record what could not be accessed or reproduced.

One real task can establish end-to-end feasibility. It cannot by itself establish productivity savings or model superiority; compare future tasks with a relevant observed baseline before making that claim.
