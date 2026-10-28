"""Build/install a real wheel in a disposable venv; never install globally."""

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(argv, cwd, *, data=None):
    result = subprocess.run(argv, cwd=cwd, input=data, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def main():
    with tempfile.TemporaryDirectory(prefix="udg-package-") as tmp:
        root = Path(tmp).resolve()
        wheels = root / "wheels"
        run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheels), str(REPO)], root)
        wheel, = wheels.glob("*.whl")
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], root)
        # Generic top-level files from co-installed packages must not shadow this
        # distribution's canonical data files. No source checkout is on sys.path.
        package_directory = Path(run([str(python), "-I", "-c",
                                      "import guardrails; print(next(iter(guardrails.__path__)))"],
                                     root).strip())
        for name in ("SKILL.md", "references/human-acceptance.md",
                     "references/risk-boundaries.md", "LICENSE"):
            unrelated = package_directory.parent / name
            unrelated.parent.mkdir(parents=True, exist_ok=True)
            unrelated.write_text("unrelated package data", encoding="utf-8")
        project = root / "project space"
        project.mkdir()
        (project / "json.py").write_text("raise RuntimeError('workspace import injection')")

        def cli(*args):
            return json.loads(run([str(python), "-I", "-m", "guardrails", *args], project))

        skill = cli("install-skill", "--workspace", str(project))
        target = Path(skill["destination"])
        for name in ("SKILL.md", "references/human-acceptance.md",
                     "references/risk-boundaries.md", "LICENSE"):
            assert (target / name).read_bytes() == (REPO / name).read_bytes(), name
        assert cli("verify-skill", "--workspace", str(project))["ok"]
        assert cli("uninstall-skill", "--workspace", str(project))["ok"]
        assert not target.exists()
        runtime = cli("install", "--workspace", str(project))
        assert runtime["mode"] == "ADAPTIVE"
        bundle = Path(runtime["destination"])
        assert cli("verify-install", "--destination", str(bundle))["ok"]
        # Execute copied runtime code, not just wheel imports. It survives without
        # loading code or assets from the user's current working directory.
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "pwd"}, "cwd": str(project)}
        output = run([str(python), "-I", str(bundle / "guardrails" / "runner.py"), "hook",
                      "--platform", "codex", "--policy", str(bundle / "policy.json"),
                      "--audit-dir", str(root / "audit")], project, data=json.dumps(event))
        assert json.loads(output) == {}
        assert not (project / ".codex").exists()
        assert not (project / ".claude").exists()
        assert (bundle / "LICENSE").read_bytes() == (REPO / "LICENSE").read_bytes()
        assert cli("uninstall", "--destination", str(bundle))["ok"]
        assert not bundle.exists()
    print("PASS: real wheel + isolated venv + Skill/runtime install/verify/uninstall + copied hook")


if __name__ == "__main__":
    main()
