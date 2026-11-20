"""Exercise the actual deployment script with a local GitHub archive substitute."""

import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="vbytsyuk-deploy-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.site = self.root / "site"
        self.script = self.root / "deploy.sh"
        source = (REPOSITORY / "deploy/deploy.sh").read_text()
        # Redirect only the destination; execute the production script otherwise.
        destination = 'site_root="/var/www/vbytsyuk.ru"'
        self.assertEqual(source.count(destination), 1)
        self.script.write_text(source.replace(destination, f'site_root="{self.site}"'))
        binary = self.root / "bin"
        binary.mkdir()
        curl = binary / "curl"
        curl.write_text("""#!/usr/bin/env bash
set -eu
[[ "${DEPLOY_TEST_DOWNLOAD_FAIL:-0}" != 1 ]] || exit 22
while [[ $# -gt 0 ]]; do
    if [[ "$1" == --output ]]; then
        cp "$DEPLOY_TEST_ARCHIVE" "$2"
        exit 0
    fi
    shift
done
exit 2
""")
        curl.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{binary}:{self.env['PATH']}"
        self.env["TMPDIR"] = str(self.root / "tmp")
        Path(self.env["TMPDIR"]).mkdir()

    def archive(self, name, *, missing=None, obsolete=False):
        source = self.root / name
        shutil.copytree(REPOSITORY / "release", source / "release")
        (source / "release/index.html").write_text(f"<h1>{name}</h1>")
        (source / "README.md").write_text("Do not publish repository files.")
        if missing:
            (source / "release" / missing).unlink()
        if obsolete:
            (source / "release/obsolete.txt").write_text("Old release only.")
        archive = self.root / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(source, arcname=f"repository-{name}")
        self.env["DEPLOY_TEST_ARCHIVE"] = str(archive)

    def run_deploy(self, *args, success=True):
        result = subprocess.run(
            ["bash", str(self.script), *args], env=self.env,
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_first_deploy_publishes_only_release_and_readable_files(self):
        self.archive("first")
        self.run_deploy()
        self.assertIn("first", (self.site / "current/index.html").read_text())
        self.assertFalse((self.site / "current/README.md").exists())
        self.assertFalse((self.site / "previous").exists())
        self.assertEqual((self.site / "current").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.site / "current/index.html").stat().st_mode & 0o777, 0o644)

    def test_update_keeps_old_release_without_obsolete_files_in_new_one(self):
        self.archive("first", obsolete=True)
        self.run_deploy()
        first = (self.site / "current").readlink()
        self.archive("second")
        self.run_deploy("v2")
        self.assertEqual((self.site / "previous").readlink(), first)
        self.assertIn("second", (self.site / "current/index.html").read_text())
        self.assertFalse((self.site / "current/obsolete.txt").exists())
        self.assertTrue((self.site / "previous/obsolete.txt").exists())

    def test_rollback_and_return_do_not_need_network(self):
        self.archive("first")
        self.run_deploy()
        self.archive("second")
        self.run_deploy()
        self.env["DEPLOY_TEST_DOWNLOAD_FAIL"] = "1"
        self.run_deploy("--rollback")
        self.assertIn("first", (self.site / "current/index.html").read_text())
        self.run_deploy("--rollback")
        self.assertIn("second", (self.site / "current/index.html").read_text())

    def test_download_failure_keeps_current_release(self):
        self.archive("first")
        self.run_deploy()
        first = (self.site / "current").readlink()
        self.env["DEPLOY_TEST_DOWNLOAD_FAIL"] = "1"
        self.run_deploy(success=False)
        self.assertEqual((self.site / "current").readlink(), first)
        self.assertEqual(len(list((self.site / "releases").iterdir())), 1)

    def test_incomplete_and_corrupt_archives_keep_current_release(self):
        self.archive("first")
        self.run_deploy()
        first = (self.site / "current").readlink()
        self.archive("incomplete", missing="styles.css")
        self.run_deploy(success=False)
        Path(self.env["DEPLOY_TEST_ARCHIVE"]).write_bytes(b"invalid archive")
        self.run_deploy(success=False)
        self.assertEqual((self.site / "current").readlink(), first)

    def test_concurrent_deploy_is_rejected(self):
        self.site.mkdir()
        with (self.site / ".deploy.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_deploy(success=False)
            self.assertIn("Другой деплой", result.stderr)
        self.assertFalse((self.site / "current").exists())

    def test_existing_current_directory_is_not_replaced(self):
        current = self.site / "current"
        current.mkdir(parents=True)
        (current / "keep.txt").write_text("keep")
        self.run_deploy(success=False)
        self.assertEqual((current / "keep.txt").read_text(), "keep")

    def test_rollback_without_previous_and_invalid_ref_fail(self):
        self.run_deploy("--rollback", success=False)
        self.run_deploy("--invalid-option", success=False)
        self.assertFalse((self.site / "current").exists())


if __name__ == "__main__":
    unittest.main()
