#!/usr/bin/env python3
"""Run a Grok implementation worker through Pi with exact-file macOS confinement."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from run_pi_advisor import (
    atomic_json,
    classify_provider_event,
    emit,
    extract_provider_usage,
    run_probe,
    sanitized_auth,
    stream_pipe,
    utc_now,
)


PROVIDER = "xai"
MODEL = "grok-4.5"
THINKING = "high"
TOOLS = "read,grep,find,ls,edit,write"
REQUIRED_HELP_FLAGS = (
    "--provider",
    "--model",
    "--thinking",
    "--mode",
    "--print",
    "--no-session",
    "--tools",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-approve",
    "--system-prompt",
)
SYSTEM_PROMPT = """You are one bounded implementation worker. The supplied task pack is authoritative.
Inspect relevant repository files and modify only the explicitly writable files enforced by the
filesystem sandbox. Do not commit, push, install dependencies, access credentials, or broaden scope.
You have no shell. Report changed files, checks you could not run, risks, and unresolved issues.
Completion is a delivery claim for Codex to review, not acceptance."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--write-file", action="append", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--attempt-id")
    parser.add_argument("--pi-bin", default="pi")
    parser.add_argument("--sandbox-bin", default="sandbox-exec")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    return parser.parse_args()


def sandbox_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def resolve_write_paths(repo_root: Path, raw_paths: list[Path]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        candidate = raw if raw.is_absolute() else repo_root / raw
        parent = candidate.parent.expanduser().resolve()
        if not parent.is_dir():
            raise SystemExit(f"write-file parent does not exist: {parent}")
        path = parent / candidate.name
        try:
            path.relative_to(repo_root)
        except ValueError as error:
            raise SystemExit(f"write-file escapes repo root: {path}") from error
        if path.exists() and path.is_symlink():
            raise SystemExit(f"write-file must not be a symlink: {path}")
        if path in seen:
            raise SystemExit(f"duplicate write-file: {path}")
        seen.add(path)
        resolved.append(path)
    return resolved


def make_profile(paths: list[Path], scratch: Path) -> str:
    allowed = [
        '  (literal "/dev/null")',
        *(f'  (literal "{sandbox_quote(str(path))}")' for path in paths),
        f'  (subpath "{sandbox_quote(str(scratch))}")',
    ]
    return "\n".join(
        (
            "(version 1)",
            "(allow default)",
            "(deny file-write*)",
            "(allow file-write*",
            *allowed,
            ")",
            "",
        )
    )


def main() -> int:
    args = parse_args()
    if args.heartbeat_seconds <= 0:
        raise SystemExit("--heartbeat-seconds must be positive")
    repo_root = args.repo_root.expanduser().resolve()
    if not repo_root.is_dir():
        raise SystemExit(f"repo root does not exist: {repo_root}")
    prompt_path = args.prompt_file.expanduser().resolve()
    if not prompt_path.is_file():
        raise SystemExit(f"prompt file does not exist: {prompt_path}")
    prompt = prompt_path.read_bytes()
    if not prompt.strip():
        raise SystemExit("prompt file is empty")
    write_paths = resolve_write_paths(repo_root, args.write_file)

    attempt_id = args.attempt_id or str(uuid.uuid4())
    try:
        uuid.UUID(attempt_id)
    except ValueError as error:
        raise SystemExit("--attempt-id must be a UUID") from error
    evidence_dir = args.evidence_root.expanduser().resolve() / attempt_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    scratch = evidence_dir / "scratch"
    pi_home = scratch / "pi-agent"
    temp_dir = scratch / "tmp"
    pi_home.mkdir(parents=True)
    temp_dir.mkdir(parents=True)
    receipt_path = evidence_dir / "receipt.json"
    stdout_path = evidence_dir / "stdout.jsonl"
    stderr_path = evidence_dir / "stderr.log"
    result_path = evidence_dir / "result.md"
    profile_path = evidence_dir / "sandbox.sb"

    version_probe = run_probe([args.pi_bin, "--version"])
    help_probe = run_probe([args.pi_bin, "--help"])
    model_probe = run_probe([args.pi_bin, "--list-models", MODEL])
    auth_probe = run_probe(
        [args.pi_bin, "auth", "check", "--provider", PROVIDER, "--model", MODEL, "--json"]
    )
    sandbox_probe = run_probe([args.sandbox_bin, "-h"])
    auth = sanitized_auth(auth_probe)
    help_text = help_probe.stdout + help_probe.stderr
    missing = [flag for flag in REQUIRED_HELP_FLAGS if flag not in help_text]
    model_available = model_probe.returncode == 0 and PROVIDER in model_probe.stdout and MODEL in model_probe.stdout
    oauth_ready = (
        auth_probe.returncode == 0
        and auth.get("status") == "ready"
        and auth.get("provider") == PROVIDER
        and auth.get("authType") == "oauth"
    )
    sandbox_available = sandbox_probe.returncode in (0, 1, 64)
    command = [
        args.sandbox_bin, "-f", str(profile_path),
        args.pi_bin,
        "--provider", PROVIDER,
        "--model", MODEL,
        "--thinking", THINKING,
        "--mode", "json",
        "--print",
        "--no-session",
        "--tools", TOOLS,
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
        "--no-approve",
        "--system-prompt", SYSTEM_PROMPT,
    ]
    receipt: dict[str, Any] = {
        "attempt_id": attempt_id,
        "status": "preflight",
        "started_at": utc_now(),
        "repo_root": str(repo_root),
        "prompt_file": str(prompt_path),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "write_files": [str(path) for path in write_paths],
        "pi_version": (version_probe.stdout or version_probe.stderr).strip(),
        "provider": PROVIDER,
        "model": MODEL,
        "thinking": THINKING,
        "tools": TOOLS.split(","),
        "auth": auth,
        "argv": command,
        "evidence": {
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "result": str(result_path),
            "sandbox_profile": str(profile_path),
        },
    }
    atomic_json(receipt_path, receipt)
    if (
        version_probe.returncode != 0
        or help_probe.returncode != 0
        or missing
        or not model_available
        or not oauth_ready
        or not sandbox_available
    ):
        receipt.update(
            status="failed_preflight",
            finished_at=utc_now(),
            missing_help_flags=missing,
            model_available=model_available,
            oauth_ready=oauth_ready,
            sandbox_available=sandbox_available,
        )
        atomic_json(receipt_path, receipt)
        emit(
            "failed_preflight",
            attempt_id=attempt_id,
            evidence_dir=str(evidence_dir),
            missing_flags=missing,
            model_available=model_available,
            oauth_ready=oauth_ready,
            sandbox_available=sandbox_available,
        )
        return 2

    bearer_probe = run_probe(
        [args.pi_bin, "auth", "print-bearer-token", "--provider", PROVIDER, "--model", MODEL]
    )
    bearer = bearer_probe.stdout.strip()
    if bearer_probe.returncode != 0 or not bearer:
        receipt.update(status="failed_credential_route", finished_at=utc_now())
        atomic_json(receipt_path, receipt)
        emit("failed_credential_route", attempt_id=attempt_id, evidence_dir=str(evidence_dir))
        return 2

    profile_path.write_text(make_profile(write_paths, scratch), encoding="utf-8")
    created_placeholders: list[str] = []
    for path in write_paths:
        if not path.exists():
            path.touch(exist_ok=False)
            created_placeholders.append(str(path))
    receipt.update(status="running", created_placeholders=created_placeholders)
    atomic_json(receipt_path, receipt)
    emit("started", attempt_id=attempt_id, evidence_dir=str(evidence_dir), model=MODEL)

    env = os.environ.copy()
    env["XAI_API_KEY"] = bearer
    env["PI_CODING_AGENT_DIR"] = str(pi_home)
    env["TMPDIR"] = str(temp_dir)
    started = time.monotonic()
    provider_result: str | None = None
    assistant_terminal = agent_end = agent_settled = False
    tool_use_detected = False
    provider_usage: dict[str, Any] | None = None
    last_phase: str | None = None
    stdout_bytes = stderr_bytes = 0
    proc: subprocess.Popen[bytes] | None = None

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=repo_root,
            env=env,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        proc.stdin.write(prompt)
        proc.stdin.close()
        events: queue.Queue[tuple[str, Any]] = queue.Queue()
        threads = [
            threading.Thread(target=stream_pipe, args=(proc.stdout, stdout_path, "stdout", events), daemon=True),
            threading.Thread(target=stream_pipe, args=(proc.stderr, stderr_path, "stderr", events), daemon=True),
        ]
        for thread in threads:
            thread.start()
        eof: set[str] = set()
        last_heartbeat = started
        while len(eof) < 2 or proc.poll() is None:
            try:
                channel, value = events.get(timeout=min(args.heartbeat_seconds, 1.0))
            except queue.Empty:
                channel, value = "", None
            if channel == "stdout":
                provider_usage = extract_provider_usage(value) or provider_usage
                phase, result, terminal, ended, settled, tool_use = classify_provider_event(
                    value,
                    expected_provider=PROVIDER,
                    expected_model=MODEL,
                )
                provider_result = result or provider_result
                assistant_terminal |= terminal
                agent_end |= ended
                agent_settled |= settled
                tool_use_detected |= tool_use
                if phase and phase != last_phase:
                    last_phase = phase
                    emit("provider_progress", attempt_id=attempt_id, phase=phase)
            elif channel == "stdout_eof":
                eof.add("stdout")
                stdout_bytes = int(value)
            elif channel == "stderr_eof":
                eof.add("stderr")
                stderr_bytes = int(value)
            now = time.monotonic()
            if now - last_heartbeat >= args.heartbeat_seconds:
                emit("heartbeat", attempt_id=attempt_id, elapsed_seconds=round(now - started, 1), phase=last_phase or "awaiting_provider_event")
                last_heartbeat = now
        for thread in threads:
            thread.join()
        process_exit = proc.wait()
    except KeyboardInterrupt:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        receipt.update(status="interrupted_unknown", finished_at=utc_now())
        atomic_json(receipt_path, receipt)
        return 130
    finally:
        bearer = ""
        env.pop("XAI_API_KEY", None)
        shutil.rmtree(scratch, ignore_errors=True)

    if provider_result is not None:
        result_path.write_text(provider_result.rstrip() + "\n", encoding="utf-8")
    if process_exit == 0 and assistant_terminal and agent_end and agent_settled and provider_result:
        status, runner_exit = "completed", 0
    elif process_exit == 0:
        status, runner_exit = "missing_terminal_result", 3
    else:
        status, runner_exit = "failed_process", process_exit if 0 < process_exit < 126 else 4
    receipt.update(
        status=status,
        finished_at=utc_now(),
        elapsed_seconds=round(time.monotonic() - started, 3),
        process_exit_code=process_exit,
        assistant_terminal=assistant_terminal,
        agent_end=agent_end,
        agent_settled=agent_settled,
        tool_use_detected=tool_use_detected,
        result_present=provider_result is not None,
        provider_usage=provider_usage,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        scratch_removed=not scratch.exists(),
    )
    atomic_json(receipt_path, receipt)
    emit(status, attempt_id=attempt_id, evidence_dir=str(evidence_dir), result_path=str(result_path) if provider_result else None)
    return runner_exit


if __name__ == "__main__":
    raise SystemExit(main())
