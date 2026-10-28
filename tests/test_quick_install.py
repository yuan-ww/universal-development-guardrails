import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from guardrails import install as installer
from guardrails.policy import Invalid

RUNNER = Path(__file__).resolve().parents[1] / "guardrails" / "runner.py"


class QuickInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(RUNNER), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def test_missing_distribution_assets_do_not_fall_back_to_unowned_files(self):
        with patch.object(installer, "distribution") as lookup:
            package = lookup.return_value
            package.locate_file.return_value = Path(installer.__file__)
            package.files = ()
            # A canonical checkout file exists, but is not owned by this record.
            with self.assertRaisesRegex(Invalid, "installation_assets_missing"):
                installer.asset("SKILL.md")

    def test_skill_roundtrip_exact_files_for_each_agent(self):
        for agent, directory in installer.SKILL_DIRECTORIES.items():
            with self.subTest(agent=agent):
                result = self.cli("install-skill", "--workspace", str(self.root), "--agent", agent)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                target = self.root / directory / "skills" / installer.SKILL_NAME
                self.assertEqual(Path(data["destination"]), target)
                self.assertEqual(data["capability"], "advisory_only")
                self.assertEqual(set(installer.verified_files(target)), set(installer.SKILL_FILES))
                for name in installer.SKILL_FILES:
                    self.assertEqual((target / name).read_bytes(), installer.asset(name).read_bytes())
                self.assertEqual(self.cli("verify-skill", "--workspace", str(self.root),
                                          "--agent", agent).returncode, 0)
                self.assertEqual(self.cli("uninstall-skill", "--workspace", str(self.root),
                                          "--agent", agent).returncode, 0)
                self.assertFalse(target.exists())

    def test_existing_modified_and_extra_user_files_survive(self):
        target = installer.install_skill(self.root)
        original = (target / "SKILL.md").read_bytes()
        (target / "SKILL.md").write_text("user changes")
        with self.assertRaises(Invalid):
            installer.install_skill(self.root)
        with self.assertRaises(Invalid):
            installer.uninstall_skill(self.root)
        self.assertEqual((target / "SKILL.md").read_text(), "user changes")
        (target / "SKILL.md").write_bytes(original)
        user = target / "user-notes.txt"
        user.write_text("keep")
        with self.assertRaises(Invalid):
            installer.uninstall_skill(self.root)
        self.assertEqual(user.read_text(), "keep")
        user.rename(self.root / "saved-notes.txt")
        extra_directory = target / "user-empty-directory"
        extra_directory.mkdir()
        with self.assertRaises(Invalid):
            installer.uninstall_skill(self.root)
        self.assertTrue(extra_directory.is_dir())
        self.assertTrue((target / "SKILL.md").is_file())

    def test_copy_failure_and_pending_skill_rejected(self):
        with patch.object(installer.shutil, "copyfile", side_effect=OSError("copy failed")):
            with self.assertRaises(OSError):
                installer.install_skill(self.root)
        target = installer.skill_destination(self.root)
        self.assertFalse(target.exists())
        installer.install_skill(self.root)
        (target / installer.PENDING).touch()
        with self.assertRaises(Invalid):
            installer.verify_skill(self.root)

    def test_publication_failure_preserves_user_edit_and_stays_pending(self):
        original = installer._publish_file
        changed = []

        def fail(source, dest):
            if changed:
                raise OSError("publish failed")
            original(source, dest)
            dest.write_text("user edit")
            changed.append(dest)

        with patch.object(installer, "_publish_file", side_effect=fail), self.assertRaises(OSError):
            installer.install_skill(self.root)
        self.assertEqual(changed[0].read_text(), "user edit")
        self.assertTrue((installer.skill_destination(self.root) / installer.PENDING).exists())
        with self.assertRaises(Invalid):
            installer.verify_skill(self.root)

    def test_symlinked_project_directories_and_global_install_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / ".agents").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(Invalid):
            installer.install_skill(self.root)
        (self.root / ".guardrails").symlink_to(outside, target_is_directory=True)
        result = self.cli("install", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(outside.iterdir()), [])
        with self.assertRaises(Invalid):
            installer.install_skill(Path.home())
        with self.assertRaises(Invalid):
            installer.install_skill(self.root, "unknown")

    def test_default_runtime_does_not_modify_host_configs(self):
        configs = {}
        for directory, name in ((".codex", "hooks.json"), (".claude", "settings.json")):
            folder = self.root / directory
            folder.mkdir()
            path = folder / name
            path.write_text('{"user":"keep"}')
            configs[path] = path.read_bytes()
        (self.root / "json.py").write_text("raise RuntimeError('untrusted workspace import')")
        result = self.cli("install", "--workspace", str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        target = self.root / ".guardrails" / "udg-bundle"
        self.assertEqual(Path(data["destination"]), target)
        self.assertEqual(data["mode"], "ADAPTIVE")
        self.assertEqual(data["activation"], "manual_hook_merge_and_trust_required")
        self.assertTrue(installer.validate_installation(target))
        self.assertEqual((target / "LICENSE").read_bytes(), installer.asset("LICENSE").read_bytes())
        self.assertEqual(configs, {p: p.read_bytes() for p in configs})
        self.assertFalse((self.root / ".agents").exists())
        self.assertEqual(self.cli("install", "--workspace", str(self.root)).returncode, 2)
