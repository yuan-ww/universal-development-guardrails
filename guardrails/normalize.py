"""Conservative syntax recognizers, NOT a shell interpreter or security sandbox."""

from __future__ import annotations

import shlex
from pathlib import Path

from .policy import Invalid, Operation, Policy, canonical, path_targets

# Even quoted metacharacters are intentionally opaque. No regex blacklist can
# explain arbitrary shell programs; this recognizer accepts only a small grammar.
META = set(";$|&><`\n\r\\*?[]{}()!~#")
GIT_READ = {"status": {"--short", "--porcelain", "--branch", "-s", "-b"},
            "diff": {"--stat", "--name-only", "--cached", "--staged", "--no-ext-diff",
                     "--no-textconv"}, "log": {"--oneline", "-1", "-5", "-10"}}


def shell(command: str, cwd: Path, policy: Policy, *, cwd_trusted=True) -> Operation:
    unknown = Operation("unknown", cwd)
    if not isinstance(command, str) or not command or len(command) > 65536:
        return unknown
    if any(c in META or ord(c) < 32 for c in command):
        return unknown
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError:
        return unknown
    if not argv or any("\x00" in a for a in argv):
        return unknown
    program, *args = argv
    # In tested Codex 0.160.0 and 0.164.0-alpha.11.1, canonical Bash input
    # does not provide a trustworthy exec_command.workdir.
    # Session cwd is not evidence of execution cwd. Only explicit absolute
    # operands (or a trustworthy host workdir extension) give scoped context.
    if program == "pwd" and not args:
        return Operation("read", cwd)
    if program == "ls":
        flags = {"-a", "-l", "-h", "-la", "-al", "-lh", "-lah", "--all", "--long"}
        paths, end_options = [], False
        for arg in args:
            if arg == "--" and not end_options:
                end_options = True
            elif arg.startswith("-") and not end_options:
                if arg not in flags:
                    return unknown
            else:
                if not cwd_trusted and not Path(arg).is_absolute():
                    return unknown
                paths.extend(path_targets(arg, cwd))
        if not cwd_trusted and not paths:
            return unknown
        return Operation("read", cwd, tuple(paths) or (cwd,), argv=argv)
    if program in {"cat", "touch"} and args and all(not a.startswith("-") for a in args):
        if not cwd_trusted and not all(Path(arg).is_absolute() for arg in args):
            return unknown
        return Operation("read" if program == "cat" else "write", cwd,
                         tuple(p for a in args for p in path_targets(a, cwd)), argv=argv)
    if program == "git" and args:
        if len(args) >= 3 and args[0] == "-C" and Path(args[1]).is_absolute():
            # One absolute -C gives Git a working directory independent of the
            # omitted execution cwd. Further global options remain unsupported.
            cwd = canonical(args[1], cwd)
            args = args[2:]
            cwd_trusted = True
        sub, *options = args
        if sub in {"reset", "clean", "checkout", "restore", "rebase", "branch"}:
            return Operation("git", cwd, categories=("destructive_git",), argv=argv)
        if sub in {"push", "fetch", "pull", "clone"}:
            cats = ("external", "destructive_git") if any(
                o.startswith("--force") or o in {"-f", "+"} or o.startswith("+")
                for o in options) else ("external",)
            return Operation("git", cwd, categories=cats, argv=argv)
        if sub in GIT_READ and all(o in GIT_READ[sub] for o in options):
            if not cwd_trusted:
                return unknown
            return Operation("git", cwd, argv=argv)
    if program in {"rm", "rmdir", "shred"}:
        # Deliberately do not guess rm option/path semantics.
        return Operation("execute", cwd, categories=("data_destruction",), argv=argv)
    if program in {"curl", "wget", "ssh", "scp", "gh"}:
        return Operation("external", cwd, argv=argv)
    if program in {"kubectl", "terraform", "ansible", "psql", "mysql"}:
        return Operation("production", cwd, argv=argv)
    # Exact operator-reviewed executions do not override known resource/risk
    # classifications above. Never populated from model-generated tool input.
    if cwd_trusted and argv in policy.development_commands:
        return Operation("development", cwd, argv=argv)
    return unknown


def patch(command, cwd):
    if (not isinstance(command, str) or not command.startswith("*** Begin Patch\n") or
            not command.rstrip().endswith("*** End Patch")):
        return Operation("unknown", cwd)
    paths, deletion = [], False
    for line in command.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: "):
            if line.startswith(prefix):
                paths.extend(path_targets(line[len(prefix):], cwd))
                deletion |= prefix == "*** Delete File: "
    if not paths:
        return Operation("unknown", cwd)
    return Operation("delete" if deletion else "write", cwd, tuple(paths))


def normalize(event, platform: str, policy: Policy) -> Operation:
    if not isinstance(event, dict) or event.get("hook_event_name") != "PreToolUse":
        raise Invalid("invalid_event")
    name, args = event.get("tool_name"), event.get("tool_input")
    if not isinstance(name, str) or not isinstance(args, dict):
        raise Invalid("invalid_tool")
    # Session cwd is host-provided; policy root is NEVER taken from the event.
    if not isinstance(event.get("cwd"), str) or not Path(event["cwd"]).is_absolute():
        raise Invalid("invalid_cwd")
    cwd = canonical(event["cwd"], policy.root)
    if name == "Bash":
        # Tested Codex events provide no trustworthy actual workdir: do not
        # substitute session cwd for execution cwd. Retain explicit extensions.
        cwd_trusted = platform != "codex" or "workdir" in args
        workdir = args.get("workdir", str(cwd))
        cwd = canonical(workdir, cwd)
        return shell(args.get("command"), cwd, policy, cwd_trusted=cwd_trusted)
    if platform == "codex" and name == "apply_patch":
        return patch(args.get("command"), cwd)
    if platform == "claude" and name in {"Read", "Write", "Edit"}:
        paths = path_targets(args.get("file_path"), cwd)
        return Operation("read" if name == "Read" else "write", cwd, paths)
    # No inference from MCP names, descriptions, approved=true, or arbitrary
    # arguments. An integration must implement and test a schema before mapping it.
    return Operation("unknown", cwd)
