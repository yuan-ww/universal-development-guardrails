"""JSON CLI. Evaluation never executes the proposed operation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluation import evaluate_traces
from .hooks import hook_main, worker
from .install import (SKILL_DIRECTORIES, default_destination, install, install_skill, uninstall,
                      uninstall_skill, validate_installation, verify_skill)
from .policy import LIMIT, MODES, Operation, Policy, error_decision, parse_json


def parser():
    result = argparse.ArgumentParser(prog="udg")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("evaluate", "validate", "_worker", "hook"):
        p = sub.add_parser(name)
        p.add_argument("--policy", required=True, type=Path)
        if name in {"hook", "_worker"}:
            p.add_argument("--platform", required=True, choices=["codex", "claude"])
        if name == "hook":
            p.add_argument("--audit-dir", required=True, type=Path)
            p.add_argument("--timeout", type=float, default=2)
    p = sub.add_parser("install")
    p.add_argument("--destination", type=Path,
                   help="new bundle directory; default: WORKSPACE/.guardrails/udg-bundle")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--mode", choices=sorted(MODES), default="OBSERVE",
                   help="first-install default: OBSERVE (audit only); PROTECT/STRICT are opt-in")
    for name in ("install-skill", "verify-skill", "uninstall-skill"):
        p = sub.add_parser(name, help="project-local text Skill only; no runtime or hooks")
        p.add_argument("--workspace", type=Path, required=True)
        p.add_argument("--agent", choices=sorted(SKILL_DIRECTORIES), default="codex")
    for name in ("uninstall", "verify-install"):
        p = sub.add_parser(name)
        p.add_argument("--destination", type=Path, required=True)
    p = sub.add_parser("evaluate-scenarios")
    p.add_argument("--trace", type=Path, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "hook":
        return hook_main(args)
    try:
        if args.command == "evaluate-scenarios":
            with args.trace.open(encoding="utf-8") as stream:
                report = evaluate_traces(parse_json(stream.read(LIMIT + 1)))
            print(json.dumps(report))
            return 0 if report["all_passed"] else 1
        if args.command == "evaluate":
            policy = Policy.load(args.policy)
            op = Operation.from_dict(parse_json(sys.stdin.read(LIMIT + 1)), policy.root)
            decision = policy.evaluate(op)
            print(json.dumps(decision.to_dict()))
            return {"ALLOW": 0, "DENY": 2, "REQUIRE_APPROVAL": 3}[decision.effective_decision]
        if args.command == "validate":
            Policy.load(args.policy)
        elif args.command == "_worker":
            print(json.dumps(worker(args.platform, args.policy, sys.stdin.read(LIMIT + 1))))
            return 0
        elif args.command == "install":
            target = args.destination or default_destination(args.workspace)
            args.destination = install(target, args.workspace, args.mode)
        elif args.command in {"install-skill", "verify-skill", "uninstall-skill"}:
            action = {"install-skill": install_skill, "verify-skill": verify_skill,
                      "uninstall-skill": uninstall_skill}[args.command]
            target = action(args.workspace, args.agent)
            print(json.dumps({"ok": True, "command": args.command, "destination": str(target),
                              "agent": args.agent, "capability": "advisory_only"}))
            return 0
        elif args.command == "uninstall":
            uninstall(args.destination)
        elif args.command == "verify-install":
            validate_installation(args.destination)
        output = {"ok": True, "command": args.command}
        if args.command == "install":
            output["mode"] = args.mode
            output["destination"] = str(args.destination)
            output["activation"] = "manual_hook_merge_and_trust_required"
            output["hook_configs"] = {platform: str(args.destination / (platform + "-hooks.json"))
                                      for platform in ("codex", "claude")}
        print(json.dumps(output))
        return 0
    except Exception:
        print(json.dumps(error_decision("invalid_input_or_configuration").to_dict()))
        return 2
