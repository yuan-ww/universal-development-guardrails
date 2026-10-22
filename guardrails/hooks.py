"""Real PreToolUse response contracts; no adapter returns a permission grant."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .policy import Decision, Invalid, LIMIT, Policy, error_decision, parse_json
from .normalize import normalize
from .storage import audit


def response(platform: str, decision: Decision, permission_mode=None):
    value = decision.effective_decision
    if value == "ALLOW":
        # In particular, NEVER return Claude's permissionDecision=allow, which
        # can skip the host's normal permission flow.
        return {}, "abstain"
    host = "deny"
    if value == "REQUIRE_APPROVAL" and platform == "claude" and permission_mode == "default":
        # Only the documented interactive permission mode. bypassPermissions,
        # acceptEdits, plan, auto and unknown modes conservatively deny here.
        host = "ask"
    reason = "UDG: " + ", ".join(decision.policy_ids) + ": " + decision.reason
    if value == "REQUIRE_APPROVAL" and host == "deny":
        reason += "; approval bridge unavailable in this host/mode; denied"
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": host,
                                   "permissionDecisionReason": reason}}, host


def worker(platform, policy_path, raw):
    policy = Policy.load(policy_path)
    event = parse_json(raw)
    op = normalize(event, platform, policy)
    decision = policy.evaluate(op)
    return {"decision": decision.to_dict(), "kind": op.kind,
            "permission_mode": event.get("permission_mode")}


def run(platform, policy_path, raw, audit_dir, timeout=2.0):
    """Internal deadline shorter than host timeout; cannot fix host launch failure."""
    kind, permission_mode = "unknown", None
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("runner.py")),
             "_worker", "--platform", platform, "--policy", str(policy_path)],
            input=raw, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode != 0 or len(result.stdout) > LIMIT:
            raise Invalid("worker_failure")
        data = parse_json(result.stdout)
        decision = Decision(**data["decision"])
        kind, permission_mode = data["kind"], data["permission_mode"]
    except Exception:  # Fail with fixed text; never echo a subprocess traceback.
        decision = error_decision("hook_worker_failed_or_timed_out")
    payload, host_response = response(platform, decision, permission_mode)
    try:
        audit(Path(audit_dir), platform, kind, decision, host_response)
    except Exception:
        if decision.mode != "OBSERVE":
            decision = error_decision("audit_unavailable")
            payload, host_response = response(platform, decision)
        else:
            # Observe does not add a blocker even if its audit sink is broken.
            payload = {"systemMessage": "UDG: audit unavailable in OBSERVE"}
    return payload, host_response


def hook_main(args):
    try:
        raw = sys.stdin.read(LIMIT + 1)
        if len(raw.encode("utf-8")) > LIMIT:
            raise Invalid("input_too_large")
        payload, _ = run(args.platform, Path(args.policy), raw, Path(args.audit_dir), args.timeout)
    except Exception:
        payload, _ = response(args.platform, error_decision())
    print(json.dumps(payload))
    return 0
