#!/usr/bin/env python3
"""Run a tool-free Fable or Opus advisory attempt through Pi with durable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ADVISOR_MODELS = {
    "fable": "claude-fable-5",
    "opus": "claude-opus-5",
}

REQUIRED_HELP_FLAGS = (
    "--provider",
    "--model",
    "--thinking",
    "--mode",
    "--print",
    "--no-session",
    "--no-tools",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-approve",
    "--system-prompt",
)

SYSTEM_PROMPT = (
    "You are an external advisory specialist. Analyze only the supplied context, "
    "preserve locked decisions, distinguish evidence from inference, and return "
    "a self-contained recommendation. You have no tools."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"launcher_event": event, **fields}, ensure_ascii=False), flush=True)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--specialist", choices=tuple(ADVISOR_MODELS), required=True)
    parser.add_argument("--thinking", choices=("off", "minimal", "low", "medium", "high", "xhigh", "max"), default="high")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--attempt-id", default=None)
    parser.add_argument("--pi-bin", default="pi")
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    return parser.parse_args()


def run_probe(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def stream_pipe(pipe: Any, destination: Path, channel: str, events: queue.Queue[tuple[str, Any]]) -> None:
    byte_count = 0
    with destination.open("wb") as output:
        while True:
            line = pipe.readline()
            if not line:
                break
            output.write(line)
            output.flush()
            byte_count += len(line)
            events.put((channel, line))
    events.put((channel + "_eof", byte_count))


def parse_json(raw_line: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def extract_provider_usage(raw_line: bytes) -> dict[str, Any] | None:
    payload = parse_json(raw_line)
    if payload is None or payload.get("type") != "message_end":
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    allowed = ("input", "output", "cacheRead", "cacheWrite", "reasoning", "totalTokens")
    sanitized: dict[str, Any] = {
        key: usage[key]
        for key in allowed
        if isinstance(usage.get(key), (int, float)) and not isinstance(usage.get(key), bool)
    }
    cost = usage.get("cost")
    if isinstance(cost, dict):
        sanitized["cost"] = {
            key: value
            for key, value in cost.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return sanitized or None


def classify_provider_event(
    raw_line: bytes,
    *,
    expected_provider: str,
    expected_model: str,
) -> tuple[str | None, str | None, bool, bool, bool, bool]:
    """Return phase, result, terminal assistant, agent end, settled, tool use."""
    payload = parse_json(raw_line)
    if payload is None:
        return None, None, False, False, False, False

    event_type = payload.get("type")
    if event_type == "message_update":
        event = payload.get("assistantMessageEvent")
        if isinstance(event, dict):
            update_type = event.get("type")
            if isinstance(update_type, str):
                if update_type.startswith("toolcall"):
                    return "tool_use", None, False, False, False, True
                if update_type.startswith("thinking"):
                    return "thinking", None, False, False, False, False
                if update_type.startswith("text"):
                    return "answer", None, False, False, False, False
        return "message_update", None, False, False, False, False

    if event_type == "message_end":
        message = payload.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            return "message_end", None, False, False, False, False
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        tool_use = any(isinstance(block, dict) and block.get("type") == "toolCall" for block in blocks)
        texts = [
            block.get("text")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        ]
        result = "\n".join(texts).strip() or None
        terminal = (
            not tool_use
            and message.get("provider") == expected_provider
            and message.get("model") == expected_model
            and message.get("stopReason") == "stop"
            and result is not None
        )
        return "assistant_terminal", result, terminal, False, False, tool_use

    if event_type == "turn_end":
        tool_results = payload.get("toolResults")
        tool_use = isinstance(tool_results, list) and bool(tool_results)
        return "turn_end", None, False, False, False, tool_use
    if event_type == "agent_end":
        return "agent_end", None, False, True, False, False
    if event_type == "agent_settled":
        return "agent_settled", None, False, False, True, False
    if isinstance(event_type, str):
        return event_type, None, False, False, False, False
    return None, None, False, False, False, False


def sanitized_auth(auth_probe: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(auth_probe.stdout)
    except json.JSONDecodeError:
        return {"valid_json": False}
    if not isinstance(payload, dict):
        return {"valid_json": False}
    allowed = ("status", "provider", "model", "authType", "source", "error")
    return {"valid_json": True, **{key: payload.get(key) for key in allowed if key in payload}}


def main() -> int:
    args = parse_args()
    if args.heartbeat_seconds <= 0:
        raise SystemExit("--heartbeat-seconds must be positive")

    prompt_path = args.prompt_file.expanduser().resolve()
    if not prompt_path.is_file():
        raise SystemExit(f"prompt file does not exist: {prompt_path}")
    prompt = prompt_path.read_bytes()
    model = ADVISOR_MODELS[args.specialist]

    attempt_id = args.attempt_id or str(uuid.uuid4())
    try:
        uuid.UUID(attempt_id)
    except ValueError as error:
        raise SystemExit("--attempt-id must be a UUID") from error

    evidence_dir = args.evidence_root.expanduser().resolve() / attempt_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = evidence_dir / "receipt.json"
    stdout_path = evidence_dir / "stdout.jsonl"
    stderr_path = evidence_dir / "stderr.log"
    result_path = evidence_dir / "result.md"

    version_probe = run_probe([args.pi_bin, "--version"])
    help_probe = run_probe([args.pi_bin, "--help"])
    model_probe = run_probe([args.pi_bin, "--list-models", model])
    auth_probe = run_probe(
        [
            args.pi_bin,
            "auth",
            "check",
            "--provider",
            "anthropic",
            "--model",
            model,
            "--json",
        ]
    )
    help_text = help_probe.stdout + help_probe.stderr
    missing = [flag for flag in REQUIRED_HELP_FLAGS if flag not in help_text]
    auth = sanitized_auth(auth_probe)
    model_available = model_probe.returncode == 0 and "anthropic" in model_probe.stdout and model in model_probe.stdout
    oauth_ready = (
        auth_probe.returncode == 0
        and auth.get("valid_json") is True
        and auth.get("status") == "ready"
        and auth.get("provider") == "anthropic"
        and auth.get("authType") == "oauth"
    )

    command = [
        args.pi_bin,
        "--provider",
        "anthropic",
        "--model",
        model,
        "--thinking",
        args.thinking,
        "--mode",
        "json",
        "--print",
        "--no-session",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
        "--no-approve",
        "--system-prompt",
        SYSTEM_PROMPT,
    ]
    receipt: dict[str, Any] = {
        "attempt_id": attempt_id,
        "status": "preflight",
        "started_at": utc_now(),
        "cwd": str(Path.cwd()),
        "prompt_file": str(prompt_path),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "pi_version": (version_probe.stdout or version_probe.stderr).strip(),
        "provider": "anthropic",
        "specialist": args.specialist,
        "model": model,
        "thinking": args.thinking,
        "auth": auth,
        "argv": command,
        "output_protocol": "pi-json-v3",
        "evidence": {
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "result": str(result_path),
        },
    }
    atomic_json(receipt_path, receipt)

    if (
        help_probe.returncode != 0
        or version_probe.returncode != 0
        or missing
        or not model_available
        or not oauth_ready
    ):
        receipt.update(
            status="failed_preflight",
            finished_at=utc_now(),
            help_exit_code=help_probe.returncode,
            version_exit_code=version_probe.returncode,
            model_exit_code=model_probe.returncode,
            auth_exit_code=auth_probe.returncode,
            missing_help_flags=missing,
            model_available=model_available,
            oauth_ready=oauth_ready,
        )
        atomic_json(receipt_path, receipt)
        emit(
            "failed_preflight",
            attempt_id=attempt_id,
            evidence_dir=str(evidence_dir),
            missing_flags=missing,
            model_available=model_available,
            oauth_ready=oauth_ready,
        )
        return 2

    receipt["status"] = "running"
    atomic_json(receipt_path, receipt)
    emit(
        "started",
        attempt_id=attempt_id,
        evidence_dir=str(evidence_dir),
        specialist=args.specialist,
        model=model,
        thinking=args.thinking,
    )

    started_monotonic = time.monotonic()
    provider_result: str | None = None
    assistant_terminal = False
    agent_end = False
    agent_settled = False
    tool_use_detected = False
    provider_usage: dict[str, Any] | None = None
    last_phase: str | None = None
    stdout_bytes = 0
    stderr_bytes = 0
    proc: subprocess.Popen[bytes] | None = None

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path.cwd(),
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

        eof_channels: set[str] = set()
        last_heartbeat = started_monotonic
        while len(eof_channels) < 2 or proc.poll() is None:
            try:
                channel, value = events.get(timeout=min(args.heartbeat_seconds, 1.0))
            except queue.Empty:
                channel, value = "", None

            if channel == "stdout":
                provider_usage = extract_provider_usage(value) or provider_usage
                phase, result, terminal, ended, settled, tool_use = classify_provider_event(
                    value,
                    expected_provider="anthropic",
                    expected_model=model,
                )
                if result is not None:
                    provider_result = result
                assistant_terminal = assistant_terminal or terminal
                agent_end = agent_end or ended
                agent_settled = agent_settled or settled
                tool_use_detected = tool_use_detected or tool_use
                if tool_use and proc.poll() is None:
                    proc.terminate()
                if phase is not None and phase != last_phase:
                    last_phase = phase
                    emit(
                        "provider_progress",
                        attempt_id=attempt_id,
                        phase=phase,
                        elapsed_seconds=round(time.monotonic() - started_monotonic, 1),
                    )
            elif channel == "stdout_eof":
                eof_channels.add("stdout")
                stdout_bytes = int(value)
            elif channel == "stderr_eof":
                eof_channels.add("stderr")
                stderr_bytes = int(value)

            now = time.monotonic()
            if now - last_heartbeat >= args.heartbeat_seconds:
                emit(
                    "heartbeat",
                    attempt_id=attempt_id,
                    elapsed_seconds=round(now - started_monotonic, 1),
                    phase=last_phase or "awaiting_provider_event",
                    process_alive=proc.poll() is None,
                )
                last_heartbeat = now

        for thread in threads:
            thread.join()
        exit_code = proc.wait()
    except KeyboardInterrupt:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        receipt.update(status="interrupted_unknown", finished_at=utc_now())
        atomic_json(receipt_path, receipt)
        emit("interrupted_unknown", attempt_id=attempt_id, evidence_dir=str(evidence_dir))
        return 130

    elapsed = round(time.monotonic() - started_monotonic, 3)
    if provider_result is not None:
        result_path.write_text(provider_result.rstrip() + "\n", encoding="utf-8")

    if tool_use_detected:
        status = "contract_violation_tool_use"
        runner_exit = 5
    elif exit_code == 0 and assistant_terminal and agent_end and agent_settled and provider_result is not None:
        status = "completed"
        runner_exit = 0
    elif exit_code == 0:
        status = "missing_terminal_result"
        runner_exit = 3
    else:
        status = "failed_process"
        runner_exit = exit_code if 0 < exit_code < 126 else 4

    receipt.update(
        status=status,
        finished_at=utc_now(),
        elapsed_seconds=elapsed,
        process_exit_code=exit_code,
        assistant_terminal=assistant_terminal,
        agent_end=agent_end,
        agent_settled=agent_settled,
        tool_use_detected=tool_use_detected,
        provider_usage=provider_usage,
        result_present=provider_result is not None,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )
    atomic_json(receipt_path, receipt)
    emit(
        status,
        attempt_id=attempt_id,
        evidence_dir=str(evidence_dir),
        elapsed_seconds=elapsed,
        process_exit_code=exit_code,
        result_path=str(result_path) if provider_result is not None else None,
    )
    return runner_exit


if __name__ == "__main__":
    raise SystemExit(main())
