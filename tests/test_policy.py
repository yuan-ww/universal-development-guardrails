import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path

from guardrails.normalize import normalize, shell
from guardrails.policy import Invalid, Operation, Policy, default_policy, parse_json


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = default_policy(self.root)
        self.policy = Policy(self.data)

    def decision(self, kind="write", paths=("src/app.txt",), **kwargs):
        data = {"kind": kind, "paths": list(paths)} | kwargs
        return self.policy.evaluate(Operation.from_dict(data, self.root))

    def test_three_decisions(self):
        self.assertEqual(self.decision().effective_decision, "ALLOW")
        self.assertEqual(self.decision(paths=(".env",)).effective_decision, "DENY")
        self.assertEqual(self.decision("delete").effective_decision, "REQUIRE_APPROVAL")

    def test_outside_and_prefix_collision(self):
        for name in ("../outside", str(self.root) + "-other/file"):
            with self.subTest(name=name):
                self.assertIn("system.outside_workspace", self.decision(paths=(name,)).policy_ids)

    def test_traversal_and_symlink(self):
        outside = self.root.parent / "outside"
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        for name in ("src/../../outside", "link/file"):
            self.assertEqual(self.decision(paths=(name,)).effective_decision, "DENY")

    def test_sensitive_read(self):
        for name in (".env", ".env.local", ".aws/credentials", ".ssh/id_ed25519"):
            self.assertEqual(self.decision("read", (name,)).effective_decision, "DENY")

    def test_symlink_cannot_hide_requested_sensitive_name(self):
        (self.root / "real-config").write_text("synthetic credential")
        (self.root / ".env").symlink_to(self.root / "real-config")
        self.assertEqual(self.decision("read", (".env",)).effective_decision, "DENY")
        self.assertEqual(self.policy.evaluate(shell("cat .env", self.root, self.policy)).effective_decision,
                         "DENY")

    def test_protection_is_component_based(self):
        self.assertEqual(self.decision(paths=(".git/config",)).effective_decision, "DENY")
        self.assertEqual(self.decision(paths=(".github/workflows/ci.yml",)).effective_decision, "ALLOW")

    def test_custom_paths_and_categories(self):
        self.data["protected_paths"] = ["production"]
        self.data["category_decisions"] = {"external": "DENY"}
        self.policy = Policy(self.data)
        self.assertEqual(self.decision(paths=("production/db",)).effective_decision, "DENY")
        self.assertEqual(self.decision("external", ()).effective_decision, "DENY")

    def test_modes(self):
        for mode, expected in (("OBSERVE", "ALLOW"), ("PROTECT", "REQUIRE_APPROVAL"),
                               ("STRICT", "DENY")):
            self.policy = Policy(self.data | {"mode": mode})
            d = self.decision("unknown", ())
            self.assertEqual(d.effective_decision, expected)
            self.assertTrue(d.policy_ids)
            self.assertTrue(d.reason)
        self.policy = Policy(self.data | {"mode": "OBSERVE"})
        d = self.decision(paths=(".env",))
        self.assertEqual((d.policy_decision, d.effective_decision), ("DENY", "ALLOW"))

    def test_priorities_and_ties(self):
        base = {"kinds": ["write"]}
        self.data["rules"] = [base | {"id": "low", "priority": 1, "decision": "DENY"},
                              base | {"id": "high", "priority": 2, "decision": "ALLOW"}]
        self.policy = Policy(self.data)
        self.assertEqual(self.decision().policy_ids, ("high",))
        self.data["rules"].append(base | {"id": "tie", "priority": 2, "decision": "DENY"})
        self.policy = Policy(self.data)
        self.assertEqual(self.decision().policy_ids, ("tie",))
        self.assertEqual(self.decision(paths=(".env",)).policy_ids, ("system.sensitive",))

    def test_rule_selectors_conjunction(self):
        self.data["rules"] = [{"id": "docs", "priority": 5, "decision": "DENY",
                               "kinds": ["write"], "path_prefixes": ["docs"]}]
        self.policy = Policy(self.data)
        self.assertEqual(self.decision(paths=("docs/a",)).effective_decision, "DENY")
        self.assertEqual(self.decision("read", ("docs/a",)).effective_decision, "ALLOW")

    def test_invalid_policies(self):
        bad = [{"mode": "wat"}, {"version": 2}, {"workspace_root": "/"},
               {"workspace_root": "relative"}, {"approved": True},
               {"category_decisions": {"production": "ALLOW"}},
               {"rules": [{"id": "x", "priority": 500, "decision": "ALLOW", "kinds": ["write"]}]},
               {"rules": [{"id": "x", "priority": True, "decision": "DENY", "kinds": ["write"]}]},
               {"development_commands": ["npm test"]}]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(Invalid):
                Policy(self.data | override)

    def test_invalid_operations(self):
        for op in (None, {}, {"kind": "magic"}, {"kind": "write"},
                   {"kind": "read", "paths": [1]}, {"kind": "read", "paths": ["\x00"]},
                   {"kind": "unknown", "approved": True},
                   {"kind": "unknown", "categories": ["safe"]}):
            with self.subTest(op=op), self.assertRaises(Invalid):
                Operation.from_dict(op, self.root)

    @unittest.skipIf(os.name == "nt", "Foreign Windows paths are native on Windows")
    def test_foreign_os_paths_are_not_reinterpreted(self):
        with self.assertRaises(Invalid):
            Operation.from_dict({"kind": "read", "paths": ["C:\\secrets"]}, self.root)

    def test_direct_unknown_operation_denied(self):
        self.assertEqual(self.policy.evaluate(Operation("bad", self.root)).effective_decision, "DENY")
        self.assertEqual(self.policy.evaluate(Operation([], self.root)).effective_decision, "DENY")
        self.assertEqual(self.policy.evaluate(Operation("write", self.root,
                                                        (self.root / ".." / "escape",))).effective_decision,
                         "DENY")

    def test_deleting_ancestor_of_protected_path_denied(self):
        self.assertEqual(self.decision("delete", (".",)).effective_decision, "DENY")

    def test_json_rejects_duplicates_nonfinite_depth_and_size(self):
        for raw in ('{"a":1,"a":2}', '{"x":NaN}', '[', 'x' * 1048577, '[' * 2000):
            with self.subTest(raw=raw[:40]), self.assertRaises(Invalid):
                parse_json(raw)

    def test_load_missing_or_invalid(self):
        path = self.root / "policy.json"
        with self.assertRaises(Invalid):
            Policy.load(path)
        path.write_bytes(b"\xff")
        with self.assertRaises(Invalid):
            Policy.load(path)
        path.write_text(json.dumps(self.data))
        self.assertEqual(Policy.load(path).root, self.root)

    def test_routine_commands(self):
        for cmd in ("pwd", "ls", "ls -la src", "git status --short", "git diff --stat", "git log --oneline -5",
                    "touch 'src with spaces.txt'", "cat README.md"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.policy.evaluate(shell(cmd, self.root, self.policy)).effective_decision,
                                 "ALLOW")

    def test_bypass_and_ambiguity_are_not_allowed(self):
        commands = ["git status; rm -rf x", "git status && curl example.com", "$(whoami)",
                    "g\\it reset --hard", "git -C ../other status", "env git reset --hard",
                    "bash -c 'git reset --hard'", "python -c 'print(1)'", "git status > .env",
                    "echo $(cat .env)", "git diff --output=.env", "git status\nrm x",
                    "git --exec-path=/tmp status", "git status | sh", "git status #ignore",
                    "cat .env", "touch ../outside", "touch .codex/hooks.json", "git push --force",
                    "git clean -fd", "rm -rf x", "kubectl delete deployment x", "curl example.com",
                    "git reset --hard", "x='git'; $x reset --hard", "echo safe", "touch *.txt",
                    'touch "unterminated', "/usr/bin/git status", "git status\x00",
                    "ls .ssh", "ls ../outside", "ls -R"]
        for cmd in commands:
            with self.subTest(cmd=cmd):
                d = self.policy.evaluate(shell(cmd, self.root, self.policy))
                self.assertNotEqual(d.effective_decision, "ALLOW")

    def test_owner_reviewed_exact_commands(self):
        self.data["development_commands"] = [["python", "-m", "unittest", "discover"]]
        policy = Policy(self.data)
        self.assertEqual(policy.evaluate(shell("python -m unittest discover", self.root, policy)).effective_decision,
                         "ALLOW")
        self.assertNotEqual(policy.evaluate(shell("python -m unittest discover x", self.root, policy)).effective_decision,
                            "ALLOW")

    def test_codex_missing_execution_cwd_does_not_trust_session_cwd(self):
        for command in ("touch ordinary.txt", "cat README.md", "ls -la", "git status"):
            event = {"hook_event_name": "PreToolUse", "cwd": str(self.root), "tool_name": "Bash",
                     "tool_input": {"command": command}}
            op = normalize(event, "codex", self.policy)
            self.assertEqual(op.kind, "unknown")
            self.assertNotEqual(self.policy.evaluate(op).effective_decision, "ALLOW")

    def test_absolute_operands_work_without_execution_cwd(self):
        root = self.root.as_posix()
        for argv in (["cat", root + "/README.md"], ["ls", root],
                     ["touch", root + "/ordinary.txt"], ["git", "-C", root, "status", "--short"]):
            command = shlex.join(argv)
            self.assertEqual(self.policy.evaluate(shell(command, self.root, self.policy,
                                                        cwd_trusted=False)).effective_decision, "ALLOW")
        outside = shlex.join(["git", "-C", self.root.parent.as_posix(), "status"])
        self.assertEqual(self.policy.evaluate(shell(outside, self.root, self.policy,
                                                    cwd_trusted=False)).effective_decision, "DENY")

    def test_allowlisted_command_cannot_authorize_unknown_execution_directory(self):
        policy = Policy(self.data | {"development_commands": [["python", "-m", "unittest"]]})
        self.assertEqual(shell("python -m unittest", self.root, policy, cwd_trusted=False).kind, "unknown")

    def test_allowlisted_commands_cannot_erase_known_risks(self):
        commands = ["touch .env", "touch ../outside", "git reset --hard", "git push origin feature"]
        self.data["development_commands"] = [c.split() for c in commands]
        policy = Policy(self.data)
        for command in commands:
            self.assertNotEqual(policy.evaluate(shell(command, self.root, policy)).effective_decision,
                                "ALLOW")

    def test_host_mapping_and_patch(self):
        def event(name, args):
            return {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": args,
                    "cwd": str(self.root)}
        for platform, name, args in (
            ("claude", "Write", {"file_path": ".env"}),
            ("claude", "Read", {"file_path": ".env"}),
            ("claude", "Edit", {"file_path": ".env"}),
            ("claude", "NotebookEdit", {"notebook_path": "ordinary.ipynb"}),
            ("codex", "apply_patch", {"command": "*** Begin Patch\n*** Add File: .env\n+x\n*** End Patch"}),
            ("codex", "Bash", {"command": "pwd", "workdir": ".."}),
            ("codex", "mcp__x__read", {"approved": True}),
        ):
            d = self.policy.evaluate(normalize(event(name, args), platform, self.policy))
            self.assertNotEqual(d.effective_decision, "ALLOW")


if __name__ == "__main__":
    unittest.main()
