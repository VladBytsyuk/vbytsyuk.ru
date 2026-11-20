"""Run the workflow's Bash step with simulated network and SSH commands."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
SHA = "a" * 40


class WorkflowDeploymentTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="vbytsyuk-ci-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        binary = self.root / "bin"
        binary.mkdir()
        commands = {
            "git": 'printf "%s\\trefs/heads/main\\n" "$CI_LATEST_SHA"',
            "ssh-keygen": "exit 0",
            "ssh": '''printf '%s\\n' "$@" > "$CI_SSH_ARGS"
cat > "$CI_SSH_INPUT"
exit "${CI_SSH_EXIT:-0}"''',
            "curl": '''touch "$CI_CURL_CALLED"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == --output ]]; then
        cp "$CI_HTML" "$2"
        exit 0
    fi
    shift
done
exit 2''',
        }
        for name, code in commands.items():
            path = binary / name
            path.write_text("#!/usr/bin/env bash\nset -eu\n" + code + "\n")
            path.chmod(0o755)
        workflow = (REPOSITORY / ".github/workflows/deploy.yml").read_text()
        self.command = textwrap.dedent(workflow.rsplit("        run: |\n", 1)[1])
        self.env = {
            **os.environ,
            "PATH": f"{binary}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(self.root),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary"),
            "GITHUB_SHA": SHA,
            "VPS_HOST": "vps.example.com",
            "VPS_USER": "site-deploy",
            "VPS_PORT": "2222",
            "VPS_SSH_KEY": "test-only-private-key",
            "VPS_KNOWN_HOSTS": "test-only-server-key",
            "CI_LATEST_SHA": SHA,
            "CI_HTML": str(REPOSITORY / "release/index.html"),
            "CI_SSH_ARGS": str(self.root / "ssh-args"),
            "CI_SSH_INPUT": str(self.root / "ssh-input"),
            "CI_CURL_CALLED": str(self.root / "curl-called"),
        }

    def run_step(self, *, success=True):
        result = subprocess.run(
            ["bash", "-c", self.command], cwd=REPOSITORY, env=self.env,
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertEqual(list(self.root.glob("vps-ssh.*")), [])
        self.assertNotIn("test-only-private-key", result.stdout + result.stderr)
        return result

    def test_deploys_tested_script_and_sha_with_pinned_host_key(self):
        self.run_step()
        args = (self.root / "ssh-args").read_text().splitlines()
        self.assertIn(f"bash -s -- {SHA}", args)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("BatchMode=yes", args)
        self.assertIn("2222", args)
        self.assertNotIn("sudo", " ".join(args))
        self.assertEqual(
            (self.root / "ssh-input").read_text(),
            (REPOSITORY / "deploy/deploy.sh").read_text(),
        )
        self.assertIn(SHA, (self.root / "summary").read_text())

    def test_missing_secret_fails_before_connecting(self):
        self.env["VPS_SSH_KEY"] = ""
        result = self.run_step(success=False)
        self.assertIn("Missing repository secret: VPS_SSH_KEY", result.stdout)
        self.assertFalse((self.root / "ssh-args").exists())

    def test_ssh_failure_stops_before_https_check(self):
        self.env["CI_SSH_EXIT"] = "255"
        self.run_step(success=False)
        self.assertFalse((self.root / "curl-called").exists())

    def test_wrong_published_html_is_a_failed_deployment(self):
        wrong = self.root / "wrong.html"
        wrong.write_text("Old version or different website")
        self.env["CI_HTML"] = str(wrong)
        self.run_step(success=False)
        self.assertFalse((self.root / "summary").exists())

    def test_old_commit_does_not_connect_to_vps(self):
        self.env["CI_LATEST_SHA"] = "b" * 40
        self.run_step()
        self.assertFalse((self.root / "ssh-args").exists())
        self.assertIn("skipped", (self.root / "summary").read_text())


if __name__ == "__main__":
    unittest.main()
