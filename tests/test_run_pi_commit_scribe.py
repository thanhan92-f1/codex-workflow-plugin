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
RUNNER = ROOT / "plugins/codex-workflow-plugin/scripts/run_pi_commit_scribe.py"


class PiCommitScribeTests(unittest.TestCase):
    def make_fake_pi(self, directory: Path, result: str) -> Path:
        flags = (
            "--provider --model --thinking --mode --print --no-session --no-tools "
            "--no-extensions --no-skills --no-prompt-templates --no-themes "
            "--no-context-files --no-approve --system-prompt"
        )
        script = directory / "pi"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import json, os, pathlib, sys
                if '--version' in sys.argv:
                    print('0.84.3'); raise SystemExit(0)
                if '--help' in sys.argv:
                    print({flags!r}); raise SystemExit(0)
                if '--list-models' in sys.argv:
                    print('openai-codex gpt-5.4-mini'); raise SystemExit(0)
                if len(sys.argv) > 2 and sys.argv[1:3] == ['auth', 'check']:
                    print(json.dumps({{'status': 'ready', 'provider': 'openai-codex', 'authType': 'oauth'}})); raise SystemExit(0)
                pathlib.Path(os.environ['FAKE_PI_ARGV']).write_text(json.dumps(sys.argv[1:]))
                pathlib.Path(os.environ['FAKE_PI_PROMPT']).write_text(sys.stdin.read())
                model = sys.argv[sys.argv.index('--model') + 1]
                print(json.dumps({{'type': 'agent_start'}}), flush=True)
                print(json.dumps({{
                    'type': 'message_end',
                    'message': {{'role': 'assistant', 'content': [{{'type': 'text', 'text': {result!r}}}],
                                'provider': 'openai-codex', 'model': model, 'stopReason': 'stop',
                                'usage': {{'input': 10, 'output': 4, 'totalTokens': 14,
                                          'cost': {{'total': 0.0001}}}}}},
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

    def invoke(self, temp: Path, result: str) -> subprocess.CompletedProcess[str]:
        request = temp / "request.md"
        diff = temp / "staged.diff"
        request.write_text("Add bounded commit workflow.", encoding="utf-8")
        diff.write_text("diff --git a/a.py b/a.py\n+print('ok')\n", encoding="utf-8")
        env = os.environ.copy()
        env["FAKE_PI_ARGV"] = str(temp / "argv.json")
        env["FAKE_PI_PROMPT"] = str(temp / "prompt.txt")
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--request-file", str(request),
                "--diff-file", str(diff),
                "--evidence-root", str(temp / "evidence"),
                "--pi-bin", str(self.make_fake_pi(temp, result)),
                "--heartbeat-seconds", "0.05",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_valid_message_is_rendered_without_authorship(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, '{"subject":"Add bounded commit workflow","body":null}')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            attempt = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["provider_usage"]["totalTokens"], 14)
            self.assertEqual(receipt["provider_usage"]["cost"]["total"], 0.0001)
            self.assertEqual((attempt / "commit-message.txt").read_text(), "Add bounded commit workflow\n")
            argv = json.loads((temp / "argv.json").read_text())
            self.assertIn("--no-tools", argv)
            self.assertEqual(argv[argv.index("--model") + 1], "gpt-5.4-mini")
            prompt = (temp / "prompt.txt").read_text()
            self.assertIn("<staged-diff>", prompt)
            self.assertIn("Add bounded commit workflow.", prompt)

    def test_coauthor_trailer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(
                temp,
                '{"subject":"Add workflow","body":"Co-authored-by: Model <model@example.com>"}',
            )
            self.assertEqual(result.returncode, 6)
            attempt = next((temp / "evidence").iterdir())
            receipt = json.loads((attempt / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "invalid_commit_message")
            self.assertFalse((attempt / "commit-message.txt").exists())

    def test_extra_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            result = self.invoke(temp, '{"subject":"Add workflow","body":null,"author":"AI"}')
            self.assertEqual(result.returncode, 6)


if __name__ == "__main__":
    unittest.main()
