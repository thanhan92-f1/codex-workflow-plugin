# Commit gate and continuation packet

Read this reference only after implementation and independent verification, when the user asks to commit or requests a handoff to a new Codex task.

## Preserve the authorization gate

Passing tests, a clean review, or a worker completion never authorizes a commit. Wait for an explicit user request to commit. That request authorizes only the commit, not push, merge, release, or deployment.

Before staging, confirm the intended paths, current branch and HEAD, current worktree state, and freshness of the checks relevant to the final diff. Never stage unrelated pre-existing changes. If the expected commit cannot be isolated, stop and surface the exact mixed paths or hunks.

## Commit scribe

The commit scribe writes text only. It has no Git or filesystem tools and never stages, commits, pushes, changes authorship, or decides scope.

After Codex stages the exact approved diff:

1. Capture the staged diff to a file with `git diff --cached --no-ext-diff --binary`. Include repository commit conventions or a few relevant existing subjects only when they are needed.
2. Check that the diff contains no credential, token, private key, or unrelated user data before sending it to an external model.
3. Create a compact request file containing the user-approved outcome and the facts the message must describe. Do not paste the conversation.
4. Run the bundled `scripts/run_pi_commit_scribe.py`. Use a durable evidence root outside the repository, such as `~/.codex/workflow-evidence/<repo>/<task>/commit-scribe`.
5. Codex reads the generated `commit-message.txt` and compares every claim to the staged diff. Reject invented issue IDs, scope, tests, or behavior.
6. Recheck the staged diff digest. If it changed after the scribe read it, discard the message and start again.
7. Commit with the reviewed message file. Do not add `Co-authored-by`, generated-by, sign-off, or model attribution.
8. Verify the new commit identity, its changed paths, and the remaining worktree. Do not push unless separately requested.

The locked candidate lower-cost route is Pi with `openai-codex/gpt-5.4-mini`, thinking `low`, OAuth, tools disabled, and ambient Pi resources disabled. If that exact route is unavailable, stop; do not silently spend a larger model or claim a cost optimization. The runner records provider-reported token usage and estimated cost when Pi supplies them. Compare those receipts across real commits; API pricing alone does not prove how a subscription OAuth route consumes account usage.

For a tiny conventional change, Codex may write the message directly when invoking another model would send more context than it saves. State that decision plainly rather than pretending the scribe was used.

## Continuation packet

After a successful commit, provide a copyable prompt for a new Codex task. The prompt is a state handoff, not a transcript summary. It must contain:

- repository path, branch, exact commit SHA, and whether the worktree remains dirty;
- completed outcome and the paths changed by the commit;
- current source-of-truth documents and relevant symbols;
- locked decisions and constraints the next task must preserve;
- checks run against the committed diff and anything still unverified;
- open findings, risks, and human decisions;
- the next requested or recommended outcome with acceptance criteria;
- the first files and commands the next task should inspect;
- an explicit instruction not to redo accepted work and not to commit or push without authorization.

Codex creates this packet because the commit scribe does not know product decisions outside the diff. If the next task is unknown, do not invent one. Produce a continuation prompt that asks the new task to inspect the recorded state and propose the next bounded task before implementation.

If the commit fails, do not emit a packet that claims the new SHA exists. Report the failure and preserve the pre-commit state.
