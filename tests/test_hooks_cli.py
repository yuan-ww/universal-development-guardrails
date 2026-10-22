import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from guardrails.hooks import run
from guardrails.install import install, uninstall, validate_installation, windows_command
from guardrails.policy import Decision, Invalid, default_policy
from guardrails.storage import audit, check_revision, revision

RUNNER = Path(__file__).resolve().parents[1] / "guardrails" / "runner.py"


def audit_once(args):
    directory, n = args
    audit(Path(directory), "codex", "write", Decision("ALLOW", "ALLOW", "ok", ("system.routine",),
                                                   "PROTECT"), "abstain")
    return n


class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps(default_policy(self.root)))
        self.audit = self.root / "audit"

    def cli(self, *args, data=""):
        return subprocess.run([sys.executable, "-I", str(RUNNER), *args], input=data, text=True,
                              capture_output=True, timeout=10)

    def event(self, name="Bash", args=None, mode="default"):
        return json.dumps({"hook_event_name": "PreToolUse", "cwd": str(self.root),
                           "tool_name": name, "tool_input": args or {"command": "git reset --hard"},
                           "permission_mode": mode})

    def hook(self, platform, raw):
        p = self.cli("hook", "--platform", platform, "--policy", str(self.policy),
                     "--audit-dir", str(self.audit), data=raw)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_contract_deny_and_ask(self):
        for platform, expected in (("codex", "deny"), ("claude", "ask")):
            out = self.hook(platform, self.event())["hookSpecificOutput"]
            self.assertEqual(out["hookEventName"], "PreToolUse")
            self.assertEqual(out["permissionDecision"], expected)
            self.assertIn("system.destructive_git", out["permissionDecisionReason"])

    def test_allow_abstains_and_never_grants_host_permission(self):
        for platform in ("codex", "claude"):
            self.assertEqual(self.hook(platform, self.event(args={"command": "pwd"})), {})

    def test_approval_unsupported_modes_deny(self):
        for mode in ("bypassPermissions", "dontAsk", "acceptEdits", "plan", "auto", "nonsense", None):
            d = self.hook("claude", self.event(mode=mode))
            self.assertEqual(d["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_observe_keeps_policy_verdict_in_audit(self):
        self.policy.write_text(json.dumps(default_policy(self.root, "OBSERVE")))
        command = shlex.join(["touch", (self.root / ".env").as_posix()])
        self.assertEqual(self.hook("codex", self.event("Bash", {"command": command})), {})
        with closing(sqlite3.connect(self.audit / "decisions.sqlite3")) as db:
            record = json.loads(db.execute("SELECT record FROM decisions").fetchone()[0])
        self.assertEqual(record["policy_decision"], "DENY")
        self.assertEqual(record["host_response"], "abstain")

    def test_invalid_input_config_and_worker_failure_deny(self):
        for raw in ("", "{", "[]", '{"hook_event_name":"PostToolUse"}', "x" * 1048577):
            self.assertEqual(self.hook("codex", raw)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.policy.write_text("{")
        self.assertEqual(self.hook("claude", self.event())["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_worker_timeout_and_crash_contract(self):
        for error in (subprocess.TimeoutExpired("worker", 1), OSError("secret-token-never-echo")):
            with patch("guardrails.hooks.subprocess.run", side_effect=error):
                out, host = run("codex", self.policy, self.event(), self.audit)
            self.assertEqual(host, "deny")
            self.assertNotIn("secret-token", json.dumps(out))

    def test_real_internal_deadline(self):
        # Real subprocess timeout (not a real Agent host timeout).
        out, host = run("codex", self.policy, self.event(), self.audit, timeout=0.000001)
        self.assertEqual(host, "deny")
        self.assertIn("timed_out", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_audit_unavailable_and_symlink(self):
        self.audit.write_text("not a directory")
        self.assertEqual(run("codex", self.policy, self.event(), self.audit)[1], "deny")
        self.policy.write_text(json.dumps(default_policy(self.root, "OBSERVE")))
        out, _ = run("codex", self.policy, self.event(), self.audit)
        self.assertIn("systemMessage", out)

    def test_no_secret_in_stdout_audit_or_stderr(self):
        secret = "token-SUPER_SECRET_VALUE"  # noqa: S105 - intentional synthetic leak canary
        raw = self.event("mcp__evil__tool", {"command": secret, "env": {"API_KEY": secret}})
        output = self.hook("codex", raw)
        self.assertNotIn(secret, json.dumps(output))
        for p in self.audit.rglob("*"):
            if p.is_file():
                self.assertNotIn(secret.encode(), p.read_bytes())

    def test_cli_exit_codes(self):
        for op, code in (({"kind": "write", "paths": ["app"]}, 0),
                         ({"kind": "read", "paths": [".env"]}, 2),
                         ({"kind": "external"}, 3), ({"kind": "write", "approved": True}, 2)):
            p = self.cli("evaluate", "--policy", str(self.policy), data=json.dumps(op))
            self.assertEqual(p.returncode, code, p.stderr)
            self.assertIn("policy_ids", json.loads(p.stdout))
        self.assertEqual(self.cli("validate", "--policy", str(self.policy)).returncode, 0)

    def test_workspace_import_injection(self):
        # -I and the absolute runner must not import a repository's json.py.
        (self.root / "json.py").write_text("raise RuntimeError('injected')")
        p = subprocess.run([sys.executable, "-I", str(RUNNER), "validate", "--policy", str(self.policy)],
                           cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_revision_detects_overlapping_edits(self):
        path = self.root / "shared"
        path.write_text("original")
        expected = revision(path)
        self.assertTrue(check_revision(path, expected))
        path.write_text("other agent's edit")
        self.assertFalse(check_revision(path, expected))
        self.assertEqual(path.read_text(), "other agent's edit")

    def test_concurrent_audit_processes(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            self.assertEqual(len(list(pool.map(audit_once, [(str(self.audit), i) for i in range(24)]))), 24)
        with closing(sqlite3.connect(self.audit / "decisions.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM decisions").fetchone()[0], 24)

    def test_audit_schema_and_insert_share_an_immediate_transaction(self):
        statements = []
        original = sqlite3.connect

        def traced(*args, **kwargs):
            db = original(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db

        with patch("guardrails.storage.sqlite3.connect", side_effect=traced):
            audit_once((str(self.audit), 0))
        self.assertEqual(statements[0], "BEGIN IMMEDIATE")
        self.assertTrue(statements[1].startswith("CREATE TABLE"))
        self.assertTrue(statements[2].startswith("INSERT INTO"))
        self.assertEqual(statements[3:], ["COMMIT"])
        with closing(original(self.audit / "decisions.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM decisions").fetchone()[0], 1)

    def test_install_verify_no_overwrite_uninstall(self):
        dest = self.root / "bundle space 'quoted'"
        install(dest, self.root)
        self.assertEqual(json.loads((dest / "policy.json").read_text())["mode"], "OBSERVE")
        self.assertTrue(validate_installation(dest))
        for platform in ("codex", "claude"):
            config = json.loads((dest / (platform + "-hooks.json")).read_text())
            hook = config["hooks"]["PreToolUse"][0]["hooks"][0]
            self.assertGreater(hook["timeout"], 2)
            if platform == "claude":
                command = [hook["command"], *hook["args"]]
            elif os.name != "nt":
                command = ["/bin/sh", "-c", hook["command"]]
            else:
                # Pass a cmd command line, not C-runtime list2cmdline escaping
                # of the /c payload (cmd.exe has a different quote grammar).
                command = 'cmd.exe /d /s /c "' + hook["commandWindows"] + '"'
            p = subprocess.run(command, input=self.event(args={"command": "pwd"}),
                               text=True, capture_output=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout), {})
        with self.assertRaises(Invalid):
            install(dest, self.root)
        # Actually run the installed entry point, which must not import the checkout.
        p = subprocess.run([sys.executable, "-I", str(dest / "guardrails" / "runner.py"),
                            "validate", "--policy", str(dest / "policy.json")], capture_output=True,
                           text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        uninstall(dest)
        self.assertFalse(dest.exists())

    def test_cli_install_default_and_explicit_modes_preserve_existing_bundle(self):
        for mode in (None, "OBSERVE", "PROTECT", "STRICT"):
            with self.subTest(mode=mode):
                dest = self.root / (mode or "default")
                args = ["install", "--workspace", str(self.root), "--destination", str(dest)]
                if mode:
                    args += ["--mode", mode]
                process = self.cli(*args)
                expected = mode or "OBSERVE"
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(json.loads(process.stdout)["mode"], expected)
                self.assertEqual(json.loads((dest / "policy.json").read_text())["mode"], expected)
                self.assertTrue(validate_installation(dest))
                before = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
                retry = self.cli("install", "--workspace", str(self.root), "--destination", str(dest))
                self.assertEqual(retry.returncode, 2)
                self.assertEqual(before, {p.relative_to(dest): p.read_bytes()
                                          for p in dest.rglob("*") if p.is_file()})

    def test_uninstall_preserves_modified_files(self):
        dest = self.root / "bundle"
        install(dest, self.root)
        (dest / "policy.json").write_text("user modified")
        with self.assertRaises(Invalid):
            uninstall(dest)
        self.assertEqual((dest / "policy.json").read_text(), "user modified")

    def test_verify_and_uninstall_reject_extra_files(self):
        dest = self.root / "bundle"
        install(dest, self.root)
        (dest / "json.py").write_text("untrusted import candidate")
        for operation in (validate_installation, uninstall):
            with self.assertRaises(Invalid):
                operation(dest)
        self.assertTrue((dest / "json.py").exists())

    def test_global_and_symlink_install_refused(self):
        for target in (Path.home(), Path.home() / ".codex" / "udg", Path("/")):
            with self.assertRaises(Invalid):
                install(target, self.root)
        link = self.root / "link"
        link.symlink_to(self.root / "target")
        with self.assertRaises(Invalid):
            install(link, self.root)

    def test_windows_command_generation_rejects_shell_expansion(self):
        for value in ("C:/%KEY%/python.exe", "C:/a&b/x", "C:/!KEY!/x", "C:/a|b/x"):
            with self.assertRaises(Invalid):
                windows_command([value, "-I"])
        self.assertEqual(windows_command(["C:/Program Files/python.exe", "-I"]),
                         '"C:/Program Files/python.exe" "-I"')


if __name__ == "__main__":
    unittest.main()
