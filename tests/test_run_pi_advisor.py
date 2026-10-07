from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plugins/codex-workflow-plugin/scripts/run_pi_advisor.py"


class PiAdvisorRunnerTests(unittest.TestCase):
    def make_fake_pi(
        self,
        directory: Path,
        *,
        complete_help: bool = True,
        auth_type: str = "oauth",
        terminal_result: bool = True,
        emit_tool_call: bool = False,
    ) -> Path:
        flags = [
            "--provider", "--model", "--thinking", "--mode", "--print",
            "--no-session", "--no-tools", "--no-extensions", "--no-skills",
            "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--no-approve", "--system-prompt",
        ]
        if not complete_help:
            flags.remove("--no-tools")
        script = directory / "pi"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json, os, pathlib, sys
                if '--version' in sys.argv:
                    print('0.84.3')
                    raise SystemExit(0)
                if '--help' in sys.argv:
                    print({' '.join(flags)!r})
                    raise SystemExit(0)
                if '--list-models' in sys.argv:
                    model = sys.argv[sys.argv.index('--list-models') + 1]
                    print(f'anthropic {{model}}')
                    raise SystemExit(0)
                if len(sys.argv) > 2 and sys.argv[1:3] == ['auth', 'check']:
                    print(json.dumps({{'status': 'ready', 'provider': 'anthropic', 'authType': {auth_type!r}}}))
                    raise SystemExit(0)
                pathlib.Path(os.environ['FAKE_PI_ARGV']).write_text(json.dumps(sys.argv[1:]))
                pathlib.Path(os.environ['FAKE_PI_PROMPT']).write_text(sys.stdin.read())
                model = sys.argv[sys.argv.index('--model') + 1]
                print(json.dumps({{'type': 'session', 'version': 3}}), flush=True)
                print(json.dumps({{'type': 'agent_start'}}), flush=True)
                print(json.dumps({{'type': 'turn_start'}}), flush=True)
                if {emit_tool_call!r}:
                    print(json.dumps({{'type': 'message_update', 'assistantMessageEvent': {{'type': 'toolcall_start', 'contentIndex': 0}}}}), flush=True)
                if {terminal_result!r}:
                    print(json.dumps({{
                        'type': 'message_end',
                        'message': {{
                            'role': 'assistant',
                            'content': [{{'type': 'text', 'text': 'advisor result'}}],
                            'provider': 'anthropic',
                            'model': model,
                            'stopReason': 'stop',
                        }},
                    }}), flush=True)
                print(json.dumps({{'type': 'turn_end', 'toolResults': []}}), flush=True)
                print(json.dumps({{'type': 'agent_end', 'messages': [], 'willRetry': False}}), flush=True)
                print(json.dumps({{'type': 'agent_settled'}}), flush=True)
                """
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def invoke(self, temp: Path, fake: Path, *, specialist: str = "opus") -> subprocess.CompletedProcess[str]:
        prompt = temp / "prompt.md"
        prompt.write_text("Review this.", encoding="utf-8")
        env = os.environ.copy()
        env["FAKE_PI_ARGV"] = str(temp / "argv.json")
        env["FAKE_PI_PROMPT"] = str(temp / "prompt-captured.md")
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--prompt-file",
                str(prompt),
                "--specialist",
                specialist,
                "--thinking",
                "high",
                "--evidence-root",
                str(temp / "evidence"),
                "--pi-bin",
                str(fake),
                "--heartbeat-seconds",
                "0.05",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_complete_stream_contract_succeeds_and_preserves_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            argv = json.loads((temp / "argv.json").read_text())
            self.assertEqual(argv[argv.index("--provider") + 1], "anthropic")
            self.assertEqual(argv[argv.index("--model") + 1], "claude-opus-5")
            self.assertEqual(argv[argv.index("--mode") + 1], "json")
            for flag in (
                "--no-session", "--no-tools", "--no-extensions", "--no-skills",
                "--no-prompt-templates", "--no-themes", "--no-context-files",
                "--no-approve",
            ):
                self.assertIn(flag, argv)
            self.assertEqual((temp / "prompt-captured.md").read_text(), "Review this.")
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "completed")
            self.assertTrue(receipt["assistant_terminal"])
            self.assertTrue(receipt["agent_end"])
            self.assertTrue(receipt["agent_settled"])
            self.assertEqual(receipt["auth"]["authType"], "oauth")
            self.assertEqual((attempt_dir / "result.md").read_text(), "advisor result\n")

    def test_fable_role_selects_the_locked_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp), specialist="fable")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            argv = json.loads((temp / "argv.json").read_text())
            self.assertEqual(argv[argv.index("--model") + 1], "claude-fable-5")

    def test_missing_required_help_flag_stops_before_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp, complete_help=False))
            self.assertEqual(result.returncode, 2)
            self.assertFalse((temp / "argv.json").exists())
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "failed_preflight")
            self.assertIn("--no-tools", receipt["missing_help_flags"])

    def test_non_oauth_auth_is_rejected_before_provider_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp, auth_type="api_key"))
            self.assertEqual(result.returncode, 2)
            self.assertFalse((temp / "argv.json").exists())
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertFalse(receipt["oauth_ready"])

    def test_exit_zero_without_terminal_assistant_message_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp, terminal_result=False))
            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "missing_terminal_result")
            self.assertFalse(receipt["assistant_terminal"])

    def test_tool_call_is_a_contract_violation(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, self.make_fake_pi(temp, emit_tool_call=True))
            self.assertEqual(result.returncode, 5, result.stderr + result.stdout)
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "contract_violation_tool_use")
            self.assertTrue(receipt["tool_use_detected"])

    def test_missing_pi_executable_is_a_recorded_preflight_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, temp / "does-not-exist")
            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            attempt_dir = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt_dir / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "failed_preflight")
            self.assertEqual(receipt["help_exit_code"], 127)


if __name__ == "__main__":
    unittest.main()
