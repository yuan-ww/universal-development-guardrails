import tempfile
import subprocess
import sys
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import patch

from guardrails import install as installer
from guardrails.policy import Invalid


def competing_install(args):
    target, workspace = map(Path, args)
    try:
        installer.install(target, workspace)
        return "installed"
    except (Invalid, FileExistsError):
        return "already_exists"


class InstallFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / "bundle"

    def assert_not_valid(self):
        with self.assertRaises((Invalid, OSError)):
            installer.validate_installation(self.target)

    def test_build_copy_failure_has_no_final_bundle(self):
        original = installer.shutil.copyfile
        calls = []

        def fail(source, dest):
            calls.append(source)
            original(source, dest)
            if len(calls) == 3:
                raise OSError("injected copy failure")

        with patch.object(installer.shutil, "copyfile", side_effect=fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob(".udg-install-*")))
        self.assert_not_valid()

    def test_policy_write_failure_has_no_final_bundle(self):
        original = Path.write_text

        def fail(path, *args, **kwargs):
            if path.name == "policy.json":
                raise OSError("injected policy failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "write_text", fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertFalse(self.target.exists())
        self.assert_not_valid()

    def test_partial_publication_is_rolled_back(self):
        original = installer._publish_file
        calls = []

        def fail(source, dest):
            if len(calls) == 4:
                raise OSError("injected publication failure")
            original(source, dest)
            calls.append(dest)
            self.assert_not_valid()

        with patch.object(installer, "_publish_file", side_effect=fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertFalse(self.target.exists())
        self.assert_not_valid()

    def test_pending_manifest_never_counts_as_valid(self):
        original = installer._publish_file

        def interrupt(source, dest):
            original(source, dest)
            if dest.name == "manifest.json":
                self.assert_not_valid()
                raise KeyboardInterrupt("interrupted after manifest copy")

        with patch.object(installer, "_publish_file", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            installer.install(self.target, self.root)
        # A just-created file that was interrupted before ownership was recorded
        # is conservatively retained, never advertised as a valid installation.
        self.assert_not_valid()
        if self.target.exists():
            self.assertTrue((self.target / installer.PENDING).exists())

    def test_rollback_preserves_user_changes_and_additions(self):
        original = installer._publish_file
        changed = []

        def fail(source, dest):
            if changed:
                raise OSError("injected failure after user edit")
            original(source, dest)
            dest.write_text("user edit during installation")
            (self.target / "user.txt").write_text("user addition")
            changed.append(dest)

        with patch.object(installer, "_publish_file", side_effect=fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertEqual(changed[0].read_text(), "user edit during installation")
        self.assertEqual((self.target / "user.txt").read_text(), "user addition")
        self.assertTrue((self.target / installer.PENDING).exists())
        self.assert_not_valid()

    def test_existing_directory_and_files_are_never_overwritten(self):
        self.target.mkdir()
        user = self.target / "policy.json"
        user.write_text("existing work")
        with self.assertRaises(Invalid):
            installer.install(self.target, self.root)
        self.assertEqual(user.read_text(), "existing work")
        self.assertEqual(list(self.target.iterdir()), [user])

    def test_file_added_after_reservation_is_not_overwritten(self):
        original = installer._publish_file
        injected = []

        def fail(source, dest):
            if not injected:
                dest.write_text("concurrent file")
                injected.append(dest)
            original(source, dest)  # xb must fail rather than replace it.

        with patch.object(installer, "_publish_file", side_effect=fail), self.assertRaises(FileExistsError):
            installer.install(self.target, self.root)
        self.assertEqual(injected[0].read_text(), "concurrent file")
        self.assert_not_valid()

    def test_competing_installers_have_one_winner(self):
        with ProcessPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(competing_install, [(str(self.target), str(self.root))] * 2))
        self.assertEqual(sorted(results), ["already_exists", "installed"])
        self.assertTrue(installer.validate_installation(self.target))

    def test_precommit_validation_failure_removes_partial_state(self):
        with patch.object(installer, "_verified_contents", side_effect=OSError("injected validation failure")):
            with self.assertRaises(OSError):
                installer.install(self.target, self.root)
        self.assertFalse(self.target.exists())
        self.assert_not_valid()

    def test_readiness_transition_failure_is_rolled_back(self):
        original = Path.unlink

        def fail(path, *args, **kwargs):
            if path == self.target / installer.PENDING:
                raise OSError("injected readiness failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assert_not_valid()

    def test_staging_cleanup_failure_happens_before_readiness(self):
        original = tempfile.TemporaryDirectory.__exit__

        def fail(instance, *args):
            self.assertTrue((self.target / installer.PENDING).exists())
            original(instance, *args)
            raise OSError("injected staging cleanup failure")

        with patch.object(tempfile.TemporaryDirectory, "__exit__", fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertFalse(self.target.exists())
        self.assert_not_valid()

    def test_partial_file_write_is_retained_but_never_ready(self):
        def fail(source, dest):
            with dest.open("xb") as stream:
                stream.write(b"incomplete bytes")
            raise OSError("injected partial write")

        with patch.object(installer, "_publish_file", side_effect=fail), self.assertRaises(OSError):
            installer.install(self.target, self.root)
        self.assertTrue((self.target / installer.PENDING).exists())
        self.assertTrue(any(p.read_bytes() == b"incomplete bytes"
                            for p in self.target.rglob("*") if p.is_file()))
        self.assert_not_valid()

    def test_nested_pending_name_is_not_ignored_as_user_file(self):
        installer.install(self.target, self.root)
        user = self.target / "guardrails" / installer.PENDING
        user.write_text("user addition")
        self.assert_not_valid()
        with self.assertRaises(Invalid):
            installer.uninstall(self.target)
        self.assertEqual(user.read_text(), "user addition")

    def test_abrupt_process_exit_leaves_only_rejected_pending_bundles(self):
        script = (
            "import os,sys; from pathlib import Path; from guardrails import install as m\n"
            "original=m._publish_file\n"
            "def crash(source,dest):\n"
            "    original(source,dest)\n"
            "    if dest.name == 'manifest.json': os._exit(17)\n"
            "m._publish_file=crash\n"
            "m.install(Path(sys.argv[1]),Path(sys.argv[2]))\n"
        )
        result = subprocess.run([sys.executable, "-c", script, str(self.target), str(self.root)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertTrue((self.target / "manifest.json").exists())
        self.assertTrue((self.target / installer.PENDING).exists())
        self.assert_not_valid()
        for stage in self.root.glob(".udg-install-*"):
            with self.assertRaises(Invalid):
                installer.validate_installation(stage)
        with self.assertRaises(Invalid):
            installer.install(self.target, self.root)
