# External specialist observability

Apply this when Codex launches Claude, Pi, or another external specialist. It addresses calls that remain silent for minutes and then become impossible to diagnose after interruption. It does not impose a reasoning-time, turn, token, or money cap.

## Prepare one attempt

Before spawn, create a fresh attempt ID and an invocation-owned evidence directory. Record the task/job link, selected CLI/provider/model/effort, sanitized argv, start time, cwd, prompt digest, expected output protocol, and whether a prior attempt may still be active. Never place credentials, environment secrets, or unrelated source in the receipt.

Inspect the installed CLI help for the exact mode. Prefer streaming structured output when supported. For Fable or Opus advisory calls, run the plugin's `scripts/run_pi_advisor.py` from the target repository root. Resolve the script relative to this installed skill (`../../scripts/run_pi_advisor.py` from the skill directory); do not copy an old cached path from another task.

The runner's required inputs are a prompt file, specialist, thinking level, and evidence root:

```bash
python3 /absolute/plugin/path/scripts/run_pi_advisor.py \
  --prompt-file /absolute/path/to/prompt.md \
  --specialist opus \
  --thinking high \
  --evidence-root /absolute/path/to/invocation-owned-evidence
```

It creates a fresh UUID directory and preflights Pi version/help, the exact Anthropic model, and OAuth readiness. The provider command fixes JSON print mode, no session, no tools, no extensions, no skills, no prompt templates, no themes, no context files, no project approval, and an explicit system prompt. It keeps raw stdout, stderr, a receipt, and the extracted result separate. Success requires the terminal assistant message, `agent_end`, `agent_settled`, provider/model identity, and no tool activity. Re-check and update the runner after Pi upgrades or preflight failures rather than improvising a partially isolated call.

Do not add a fallback model, token/money cap, max turns, or an equivalent internal reasoning limit. Preserve the selected specialist. This alpha keeps advisory tools disabled; Codex supplies source and repository evidence in the prompt pack.

## Observe without blocking the conversation

Launch the runner through an executor that yields promptly and provides a live session/process handle. Do not leave one blocking shell call waiting until a buffered final response. The runner emits compact lifecycle and heartbeat JSON while preserving the provider stream in its evidence directory. Poll in bounded intervals and send concise commentary before the user has been left without an update for 60 seconds.

On silence, inspect distinct signals:

- process liveness and elapsed time;
- stdout/stderr/debug file growth;
- parsed progress, partial assistant events, tool activity, or terminal events;
- CLI/service health when the evidence warrants it.

Silence or long model effort alone is not proof that the process is stuck. State what is observed and what remains unknown. Do not promise a completion time from elapsed time alone.

Interrupt only for an actual error, safety conflict, demonstrated non-progress, unrecoverable tool loop, or user cancellation. A user asking why the call is slow authorizes diagnosis, not an automatic duplicate launch.

## Finish, interrupt, or retry

Record process exit and native terminal evidence separately from the semantic result. A final answer buffered at exit can still be valid; exit zero without a matching terminal result is not completion.

After an interrupt, verify the owned process has ended and retain the partial evidence. Mark the attempt `interrupted_unknown` unless native evidence proves a known failure. A generic `Execution error` printed after Ctrl-C does not establish that the provider failed before interruption.

Retry only as a fresh attempt with a new ID after confirming the prior process ended and obtaining user approval when the previous completion is unknown. Link the attempts; never overwrite the first receipt. A narrower prompt or different output mode may improve diagnosis, but do not silently change the selected model/provider or claim the retry resumed the original work.

At handoff, report useful wait time, user interventions, whether partial progress was visible, the exact reason for interruption, and what the evidence can and cannot establish.
