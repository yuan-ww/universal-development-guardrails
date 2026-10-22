"""Small deterministic policy core, independent of any agent or shell."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

LIMIT = 1_048_576
DECISIONS = {"ALLOW", "DENY", "REQUIRE_APPROVAL"}
MODES = {"OBSERVE", "PROTECT", "STRICT"}
KINDS = {"read", "write", "delete", "git", "development", "execute", "external", "production", "unknown"}
CATEGORIES = {"destructive_git", "data_destruction", "external", "production", "opaque_execution"}
RANK = {"ALLOW": 0, "REQUIRE_APPROVAL": 1, "DENY": 2}
ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


class Invalid(ValueError):
    """Messages are fixed codes: never echo input, paths, commands, or secrets."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid("duplicate_key")
        result[key] = value
    return result


def parse_json(raw: str) -> Any:
    if len(raw.encode("utf-8")) > LIMIT:
        raise Invalid("input_too_large")
    try:
        return json.loads(raw, object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Invalid("non_finite")))
    except (ValueError, RecursionError) as exc:
        raise Invalid("invalid_json") from exc


def strings(value, *, empty=True):
    if not isinstance(value, list) or len(value) > 1024:
        raise Invalid("invalid_list")
    if any(not isinstance(x, str) or not x or len(x) > 4096 or "\x00" in x for x in value):
        raise Invalid("invalid_string")
    if not empty and not value:
        raise Invalid("empty_list")
    return tuple(value)


def canonical(value: str, cwd: Path) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 4096:
        raise Invalid("invalid_path")
    # Never reinterpret a foreign OS drive/UNC path as a harmless relative name.
    if os.name != "nt" and (PureWindowsPath(value).drive or "\\" in value):
        raise Invalid("foreign_path")
    if value.startswith("~") or "$" in value:
        raise Invalid("unexpanded_path")
    try:
        return (cwd / value).resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise Invalid("unresolvable_path") from exc


def within(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def path_targets(value: str, cwd: Path) -> tuple[Path, ...]:
    """Check both requested spelling and resolved target; symlinks cannot hide .env."""
    resolved = canonical(value, cwd)
    lexical = Path(os.path.abspath(cwd / value))
    return tuple(dict.fromkeys((lexical, resolved)))


@dataclass(frozen=True)
class Operation:
    kind: str
    cwd: Path
    paths: tuple[Path, ...] = ()
    categories: tuple[str, ...] = ()
    argv: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data, root: Path):
        if not isinstance(data, dict) or set(data) - {"kind", "cwd", "paths", "categories", "argv"}:
            raise Invalid("invalid_operation")
        if not isinstance(data.get("kind"), str) or data["kind"] not in KINDS:
            raise Invalid("unknown_kind")
        cwd = canonical(data.get("cwd", str(root)), root)
        paths = tuple(p for x in strings(data.get("paths", [])) for p in path_targets(x, cwd))
        categories = strings(data.get("categories", []))
        if not set(categories) <= CATEGORIES:
            raise Invalid("unknown_category")
        argv = strings(data.get("argv", []))
        kind = data["kind"]
        if kind in {"read", "write", "delete"} and not paths:
            raise Invalid("missing_paths")
        return cls(kind, cwd, paths, categories, argv)


@dataclass(frozen=True)
class Decision:
    policy_decision: str
    effective_decision: str
    reason: str
    policy_ids: tuple[str, ...]
    mode: str

    def to_dict(self):
        return asdict(self)


def error_decision(code="invalid_input"):
    return Decision("DENY", "DENY", code, ("system.invalid",), "UNKNOWN")


class Policy:
    def __init__(self, data: dict):
        fields = {"version", "mode", "workspace_root", "protected_paths", "sensitive_names",
                  "category_decisions", "rules", "development_commands"}
        if (not isinstance(data, dict) or set(data) - fields or
                type(data.get("version")) is not int or data["version"] != 1):
            raise Invalid("invalid_policy")
        if not isinstance(data.get("mode"), str) or data["mode"] not in MODES:
            raise Invalid("invalid_mode")
        root = data.get("workspace_root")
        if not isinstance(root, str) or not Path(root).is_absolute():
            raise Invalid("absolute_workspace_required")
        self.root = canonical(root, Path.cwd())
        if self.root == Path(self.root.anchor) or not self.root.is_dir():
            raise Invalid("unsafe_workspace")
        self.mode = data["mode"]
        self.protected = tuple(target for p in
                               strings(data.get("protected_paths", [".git", ".codex", ".claude",
                                                                      ".cursor", ".guardrails"]))
                               for target in path_targets(p, self.root))
        self.sensitive = strings(data.get("sensitive_names", [".env", ".ssh", ".aws",
                                                               "credentials", "id_rsa", "id_ed25519"]))
        decisions = data.get("category_decisions", {})
        if (not isinstance(decisions, dict) or not set(decisions) <= CATEGORIES or
                any(not isinstance(v, str) or v not in {"DENY", "REQUIRE_APPROVAL"}
                    for v in decisions.values())):
            raise Invalid("invalid_category_decisions")
        self.category_decisions = {c: "REQUIRE_APPROVAL" for c in CATEGORIES} | decisions
        commands = data.get("development_commands", [])
        if not isinstance(commands, list) or len(commands) > 256:
            raise Invalid("invalid_development_commands")
        self.development_commands = tuple(strings(c, empty=False) for c in commands)
        rules = data.get("rules", [])
        if not isinstance(rules, list) or len(rules) > 256:
            raise Invalid("invalid_rules")
        ids = set()
        self.rules = []
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) - {"id", "priority", "decision", "kinds",
                                                        "categories", "path_prefixes"}:
                raise Invalid("invalid_rule")
            ident = rule.get("id")
            priority = rule.get("priority")
            if (not isinstance(ident, str) or not ID.fullmatch(ident) or ident in ids or
                    ident.startswith("system.") or type(priority) is not int or
                    not 0 <= priority <= 499 or not isinstance(rule.get("decision"), str) or
                    rule["decision"] not in DECISIONS):
                raise Invalid("invalid_rule")
            kinds = strings(rule.get("kinds", []))
            cats = strings(rule.get("categories", []))
            paths = tuple(canonical(p, self.root) for p in strings(rule.get("path_prefixes", [])))
            if not set(kinds) <= KINDS or not set(cats) <= CATEGORIES or not (kinds or cats or paths):
                raise Invalid("invalid_rule_selector")
            ids.add(ident)
            self.rules.append((ident, priority, rule["decision"], kinds, cats, paths))

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as stream:
                raw = stream.read(LIMIT + 1)
            return cls(parse_json(raw))
        except (OSError, UnicodeError, TypeError) as exc:
            raise Invalid("policy_unavailable") from exc

    def evaluate(self, op: Operation) -> Decision:
        if (not isinstance(op, Operation) or not isinstance(op.kind, str) or op.kind not in KINDS or
                not isinstance(op.cwd, Path) or not op.cwd.is_absolute() or
                not isinstance(op.paths, tuple) or not isinstance(op.categories, tuple) or
                any(not isinstance(p, Path) or not p.is_absolute() for p in op.paths) or
                any(not isinstance(c, str) or c not in CATEGORIES for c in op.categories) or
                (op.kind in {"write", "delete"} and not op.paths)):
            return error_decision("invalid_operation")
        try:
            op = Operation(op.kind, canonical(str(op.cwd), self.root),
                           tuple(p for target in op.paths for p in path_targets(str(target), self.root)),
                           op.categories, op.argv)
        except Invalid:
            return error_decision("invalid_operation")
        candidates = [(0, "ALLOW", "system.routine", "Routine scoped operation")]

        def add(priority, decision, ident, reason):
            candidates.append((priority, decision, ident, reason))

        if not within(op.cwd, self.root) or any(not within(p, self.root) for p in op.paths):
            add(800, "DENY", "system.outside_workspace", "Target is outside the configured workspace")
        if any(part in self.sensitive or part.startswith(".env.") for part in op.cwd.parts):
            add(900, "DENY", "system.sensitive", "Sensitive resource access is denied")
        for path in op.paths:
            if any(part in self.sensitive or part.startswith(".env.") for part in path.parts):
                add(900, "DENY", "system.sensitive", "Sensitive resource access is denied")
            if op.kind != "read" and any(within(path, p) or
                                         (op.kind == "delete" and within(p, path))
                                         for p in self.protected):
                add(900, "DENY", "system.protected", "Protected resource modification is denied")
        if op.kind == "unknown":
            add(700, "DENY" if self.mode == "STRICT" else "REQUIRE_APPROVAL",
                "system.unknown", "Operation is not reliably classified")
        categories = set(op.categories)
        categories.update({"delete": ["data_destruction"], "external": ["external"],
                           "production": ["production"], "execute": ["opaque_execution"]}.get(op.kind, []))
        for cat in sorted(categories):
            decision = self.category_decisions[cat]
            if self.mode == "STRICT" and cat == "opaque_execution":
                decision = "DENY"
            add(600, decision, "system." + cat, "Sensitive operation requires host authorization")
        for ident, priority, decision, kinds, cats, paths in self.rules:
            if ((not kinds or op.kind in kinds) and (not cats or set(cats) & categories) and
                    (not paths or any(within(p, prefix) for p in op.paths for prefix in paths))):
                add(priority, decision, ident, "Configured policy matched")
        priority = max(c[0] for c in candidates)
        finalists = sorted((c for c in candidates if c[0] == priority), key=lambda c: c[2])
        result = max(finalists, key=lambda c: RANK[c[1]])
        ids = tuple(c[2] for c in finalists if c[1] == result[1])
        effective = "ALLOW" if self.mode == "OBSERVE" else result[1]
        return Decision(result[1], effective, result[3], ids, self.mode)


def default_policy(root: Path, mode="PROTECT"):
    return {"version": 1, "mode": mode, "workspace_root": str(root.resolve()),
            "protected_paths": [".git", ".codex", ".claude", ".cursor", ".guardrails"],
            "rules": [], "development_commands": []}
