"""Create-only local bundles. Activation is an explicit host configuration merge."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from .policy import Invalid, Policy, default_policy, parse_json, within

PENDING = ".udg-installing"
SKILL_NAME = "universal-development-guardrails"
SKILL_FILES = ("SKILL.md", "references/risk-boundaries.md", "LICENSE")
SKILL_DIRECTORIES = {"codex": ".agents", "claude": ".claude", "cursor": ".cursor"}


def asset(name):
    """Resolve canonical checkout files or the wheel's installed data files."""
    if name not in SKILL_FILES:
        raise Invalid("unknown_asset")
    module = Path(__file__).resolve()
    try:
        package = distribution(SKILL_NAME)
        # Only the distribution owning this imported module may supply assets.
        # In a wheel, the module's parent is site-packages: generic files there
        # can belong to other packages and must never shadow our data files.
        if Path(package.locate_file("guardrails/install.py")).resolve() == module:
            suffix = "share/" + SKILL_NAME + "/" + name
            # Source egg-info lists canonical assets directly; wheel RECORD
            # lists the installed share directory. Both must belong to us.
            matches = [package.locate_file(p) for p in package.files or ()
                       if p.as_posix() == name or p.as_posix().endswith(suffix)]
            if len(matches) == 1 and matches[0].is_file():
                return matches[0]
            raise Invalid("installation_assets_missing")
    except PackageNotFoundError:
        pass
    # Checkout (including editable installs) or a copied runtime bundle. Do not
    # select assets from an unrelated globally installed version of this project.
    source = module.parent.parent / name
    if source.is_file():
        return source
    raise Invalid("installation_assets_missing")


def _write_manifest(staging):
    files = {p.relative_to(staging).as_posix(): digest(p) for p in staging.rglob("*")
             if p.is_file() and p != staging / PENDING}
    (staging / "manifest.json").write_text(json.dumps({"version": 1, "files": files}, indent=2) + "\n",
                                          encoding="utf-8")


def windows_command(argv):
    # list2cmdline quotes for the C argv parser, not for cmd.exe expansion.
    # Reject expansion/metacharacters rather than treating it as shell escaping.
    if any(any(c in arg for c in '%!^&|<>"\r\n') for arg in argv):
        raise Invalid("unsupported_windows_command_path")
    # Quote every token so parentheses and spaces remain literal in cmd.exe.
    return " ".join('"' + arg.rstrip("\\") + "\\" * (2 * (len(arg) - len(arg.rstrip("\\")))) + '"'
                    for arg in argv)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def destination(path):
    path = Path(path)
    if path.is_symlink():
        raise Invalid("symlink_destination")
    path = path.resolve()
    home = Path.home().resolve()
    if path == Path(path.anchor) or path == home or any(
            within(path, home / p) for p in (".codex", ".claude", ".cursor", ".agents")):
        raise Invalid("global_destination_forbidden")
    return path


def _build_bundle(staging: Path, target: Path, workspace: Path, mode):
    """Build privately; commands refer to the final path, never the temporary one."""
    data = default_policy(workspace, mode)
    data["protected_paths"].append(str(target))
    Policy(data)
    package = staging / "guardrails"
    package.mkdir()
    for source in Path(__file__).parent.glob("*.py"):
        shutil.copyfile(source, package / source.name)
    shutil.copyfile(asset("LICENSE"), staging / "LICENSE")
    (staging / "policy.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    # cmd.exe quoting is distinct from POSIX shell quoting. Both are generated;
    # Windows activation remains unverified until exercised on a Windows host.
    argv = [sys.executable, "-I", str(target / "guardrails" / "runner.py"), "hook", "--platform"]
    for platform in ("codex", "claude"):
        args = argv + [platform, "--policy", str(target / "policy.json"),
                       "--audit-dir", str(target.parent / (target.name + "-audit"))]
        command = shlex.join(args)
        handler = {"type": "command", "command": command, "timeout": 5}
        if platform == "claude":
            # Current Claude command exec form avoids a shell, including on
            # Windows. Host support still requires real version verification.
            handler["command"] = args[0]
            handler["args"] = args[1:]
            handler["onFailure"] = "block"
        else:
            try:
                handler["commandWindows"] = windows_command(args)
            except Invalid:
                if os.name == "nt":
                    raise
                # The POSIX bundle remains useful, but never emit a Windows
                # command that might expand a user-controlled directory name.
                handler["commandWindows"] = "exit 2"
        snippet = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [handler]}]}}
        (staging / (platform + "-hooks.json")).write_text(
            json.dumps(snippet, indent=2) + "\n", encoding="utf-8")
    _write_manifest(staging)


def _publish_file(source, target):
    # Exclusive creation: even a file added after directory reservation survives.
    with target.open("xb") as stream:
        stream.write(source.read_bytes())


def _rollback(target, owned_files, owned_dirs):
    """Remove only files we created that still match our bytes; never rmtree target."""
    for path, checksum in reversed(owned_files):
        try:
            if not path.is_symlink() and path.is_file() and digest(path) == checksum:
                path.unlink()
        except OSError:
            pass  # A retained file is safer than deleting an unverified change.
    for directory in reversed(owned_dirs):
        try:
            directory.rmdir()  # Non-empty directories (user additions) survive.
        except OSError:
            pass


def install(target: Path, workspace: Path, mode="OBSERVE"):
    target = destination(target)
    workspace = workspace.resolve()
    Policy(default_policy(workspace, mode))
    return _create_bundle(target, lambda staging: _build_bundle(staging, target, workspace, mode),
                          lambda: Policy.load(target / "policy.json"))


def default_destination(workspace):
    workspace = Path(workspace).resolve()
    target = workspace / ".guardrails" / "udg-bundle"
    if target.is_symlink() or target.parent.is_symlink() or not within(target.resolve(), workspace):
        raise Invalid("symlink_destination")
    return target


def _create_bundle(target, build, validate=None):
    """Shared create-only publication for concrete runtime and text Skill bundles."""
    if target.exists():
        raise Invalid("destination_exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    owned_files, owned_dirs = [], []
    reserved = False
    pending_owned = False
    # A killed build can leave a private staging directory, always marked pending.
    try:
        with tempfile.TemporaryDirectory(prefix=".udg-install-", dir=target.parent) as tmp:
            staging = Path(tmp)
            (staging / PENDING).write_bytes(b"incomplete installation\n")
            build(staging)
            sources = sorted((p for p in staging.rglob("*") if p.is_file() and p != staging / PENDING),
                             key=lambda p: (p.name == "manifest.json", p.as_posix()))
            target.mkdir(mode=0o700)  # Atomic reservation, never replace an existing directory.
            reserved = True
            owned_dirs.append(target)
            with (target / PENDING).open("xb") as stream:
                pending_owned = True
                stream.write(b"incomplete installation\n")
            for source in sources:
                dest = target / source.relative_to(staging)
                if dest.parent != target and not dest.parent.exists():
                    dest.parent.mkdir(mode=0o700)
                    owned_dirs.append(dest.parent)
                # Record ownership only after exclusive open succeeded. Do not
                # remove somebody else's file when publication raises FileExistsError.
                _publish_file(source, dest)
                owned_files.append((dest, digest(source)))
            if validate is not None:
                validate()
            _verified_contents(target)
        # Even staging cleanup must succeed before the final readiness transition.
        (target / PENDING).unlink()
    except BaseException:
        if reserved:
            if pending_owned and not (target / PENDING).exists():
                try:
                    with (target / PENDING).open("xb") as stream:
                        stream.write(b"incomplete installation\n")
                except OSError:
                    pass
            # Keep the marker while cleaning up. If user changes remain,
            # validation must reject the retained partial bundle.
            _rollback(target, owned_files, owned_dirs[1:])
            try:
                if (pending_owned and list(target.iterdir()) == [target / PENDING] and
                        not (target / PENDING).is_symlink() and
                        (target / PENDING).read_bytes() == b"incomplete installation\n"):
                    (target / PENDING).unlink()
                    target.rmdir()
            except OSError:
                pass
        raise
    return target


def skill_destination(workspace, agent="codex"):
    workspace = Path(workspace).resolve()
    Policy(default_policy(workspace))  # Existing directory; not a filesystem root.
    if agent not in SKILL_DIRECTORIES:
        raise Invalid("unknown_agent")
    target = workspace / SKILL_DIRECTORIES[agent] / "skills" / SKILL_NAME
    for parent in (target, target.parent, target.parent.parent):
        if parent.is_symlink():
            raise Invalid("symlink_destination")
    target = destination(target)
    if not within(target, workspace):
        raise Invalid("outside_workspace")
    return target


def install_skill(workspace, agent="codex"):
    target = skill_destination(workspace, agent)

    def build(staging):
        for name in SKILL_FILES:
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset(name), dest)
        _write_manifest(staging)

    return _create_bundle(target, build)


def verify_skill(workspace, agent="codex"):
    target = skill_destination(workspace, agent)
    if set(verified_files(target)) != set(SKILL_FILES):
        raise Invalid("invalid_skill_bundle")
    return target


def uninstall_skill(workspace, agent="codex"):
    target = verify_skill(workspace, agent)
    uninstall(target)
    return target


def verified_files(target: Path):
    if (target / PENDING).exists() or (target / PENDING).is_symlink():
        raise Invalid("incomplete_installation")
    return _verified_contents(target)


def _verified_contents(target: Path):
    """Content check before the installer commits readiness, not an activation API."""
    manifest_path = target / "manifest.json"
    if manifest_path.is_symlink():
        raise Invalid("modified_installation")
    with manifest_path.open(encoding="utf-8") as stream:
        manifest = parse_json(stream.read(1_048_577))
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise Invalid("invalid_manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise Invalid("invalid_manifest")
    if any(not isinstance(name, str) or not isinstance(checksum, str)
           for name, checksum in files.items()):
        raise Invalid("invalid_manifest")
    expected = set(files) | {"manifest.json"}
    expected_dirs = {parent.as_posix() for name in files for parent in Path(name).parents
                     if parent != Path(".")}
    actual, actual_dirs = set(), set()
    for path in target.rglob("*"):
        if path.is_symlink():
            raise Invalid("modified_installation")
        if path.is_file():
            if path != target / PENDING:
                actual.add(path.relative_to(target).as_posix())
        elif path.is_dir():
            actual_dirs.add(path.relative_to(target).as_posix())
        else:
            raise Invalid("modified_installation")
    if actual != expected or actual_dirs != expected_dirs:
        raise Invalid("modified_installation")
    for name, checksum in files.items():
        path = target / name
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts or
                not within(path.resolve(), target) or not path.is_file() or digest(path) != checksum):
            raise Invalid("modified_installation")
    return files


def uninstall(target: Path):
    target = destination(target)
    files = verified_files(target)
    # Complete preflight before removal; preserve modified/extra user files.
    for name in files:
        (target / name).unlink()
    (target / "manifest.json").unlink()
    for path in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            path.rmdir()
    target.rmdir()


def validate_installation(target):
    """Read-only checksum validation, useful before host hook trust review."""
    target = destination(target)
    verified_files(target)
    Policy.load(target / "policy.json")
    return True
