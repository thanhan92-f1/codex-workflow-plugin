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
RUNNER = ROOT / "plugins/codex-workflow-plugin/scripts/run_pi_writer.py"


class PiWriterTests(unittest.TestCase):
    def make_fake_pi(self, directory: Path) -> Path:
        flags = (
            "--provider --model --thinking --mode --print --no-session --tools "
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
                    print('xai grok-4.5'); raise SystemExit(0)
                if len(sys.argv) > 2 and sys.argv[1:3] == ['auth', 'check']:
                    print(json.dumps({{'status': 'ready', 'provider': 'xai', 'authType': 'oauth'}})); raise SystemExit(0)
                if len(sys.argv) > 2 and sys.argv[1:3] == ['auth', 'print-bearer-token']:
                    print('secret-bearer-value'); raise SystemExit(0)
                pathlib.Path(os.environ['FAKE_PI_ARGV']).write_text(json.dumps(sys.argv[1:]))
                pathlib.Path(os.environ['FAKE_PI_ENV']).write_text(json.dumps({{
                    'xai_key': os.environ.get('XAI_API_KEY'),
                    'pi_dir': os.environ.get('PI_CODING_AGENT_DIR'),
                    'tmp': os.environ.get('TMPDIR'),
                }}))
                pathlib.Path(os.environ['FAKE_WRITE_PATH']).write_text('worker output\\n')
                model = sys.argv[sys.argv.index('--model') + 1]
                print(json.dumps({{'type': 'agent_start'}}), flush=True)
                print(json.dumps({{'type': 'message_update', 'assistantMessageEvent': {{'type': 'toolcall_start'}}}}), flush=True)
                print(json.dumps({{
                    'type': 'message_end',
                    'message': {{'role': 'assistant', 'content': [{{'type': 'text', 'text': 'implemented'}}],
                                'provider': 'xai', 'model': model, 'stopReason': 'stop',
                                'usage': {{'input': 20, 'output': 8, 'totalTokens': 28,
                                          'cost': {{'total': 0.001}}}}}},
                }}), flush=True)
                print(json.dumps({{'type': 'turn_end', 'toolResults': [{{'ok': True}}]}}), flush=True)
                print(json.dumps({{'type': 'agent_end', 'messages': [], 'willRetry': False}}), flush=True)
                print(json.dumps({{'type': 'agent_settled'}}), flush=True)
                """
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def make_fake_sandbox(self, directory: Path) -> Path:
        script = directory / "sandbox-exec"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import os, subprocess, sys
                if sys.argv[1:] == ['-h']:
                    print('fake sandbox'); raise SystemExit(0)
                if len(sys.argv) < 4 or sys.argv[1] != '-f':
                    raise SystemExit(64)
                raise SystemExit(subprocess.call(sys.argv[3:], env=os.environ.copy()))
                """
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_writer_uses_oauth_env_no_bash_and_durable_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            repo = temp / "repo"
            repo.mkdir()
            prompt = temp / "prompt.md"
            prompt.write_text("Write only allowed.txt", encoding="utf-8")
            target = repo / "allowed.txt"
            env = os.environ.copy()
            env["FAKE_PI_ARGV"] = str(temp / "argv.json")
            env["FAKE_PI_ENV"] = str(temp / "env.json")
            env["FAKE_WRITE_PATH"] = str(target)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--prompt-file", str(prompt),
                    "--repo-root", str(repo),
                    "--write-file", "allowed.txt",
                    "--evidence-root", str(temp / "evidence"),
                    "--pi-bin", str(self.make_fake_pi(temp)),
                    "--sandbox-bin", str(self.make_fake_sandbox(temp)),
                    "--heartbeat-seconds", "0.05",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_text(), "worker output\n")
            attempt = next((temp / "evidence").iterdir())
            receipt_text = (attempt / "receipt.json").read_text()
            receipt = json.loads(receipt_text)
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["provider_usage"]["totalTokens"], 28)
            self.assertTrue(receipt["scratch_removed"])
            self.assertFalse((attempt / "scratch").exists())
            self.assertEqual(receipt["write_files"], [str(target.resolve())])
            self.assertIn(str(target.resolve()), (attempt / "sandbox.sb").read_text())
            self.assertNotIn("secret-bearer-value", receipt_text)
            argv = json.loads((temp / "argv.json").read_text())
            tools = argv[argv.index("--tools") + 1].split(",")
            self.assertNotIn("bash", tools)
            child_env = json.loads((temp / "env.json").read_text())
            self.assertEqual(child_env["xai_key"], "secret-bearer-value")
            self.assertTrue(child_env["pi_dir"].startswith(str(attempt.resolve())))
            self.assertTrue(child_env["tmp"].startswith(str(attempt.resolve())))

    def test_path_outside_repo_fails_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp = Path(raw_temp)
            repo = temp / "repo"
            repo.mkdir()
            prompt = temp / "prompt.md"
            prompt.write_text("No writes", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--prompt-file", str(prompt),
                    "--repo-root", str(repo),
                    "--write-file", str(temp / "outside.txt"),
                    "--evidence-root", str(temp / "evidence"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("escapes repo root", result.stderr)


if __name__ == "__main__":
    unittest.main()
