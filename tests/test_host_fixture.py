import os
import unittest
from pathlib import Path
from unittest.mock import patch

from integration.codex_host import isolated_environment


class HostFixtureTests(unittest.TestCase):
    def test_inherited_environment_cannot_redirect_git_or_python_controls(self):
        inherited = {"PATH": "known-path", "HOME": "known-home", "LC_ALL": "C",
                     "GIT_DIR": "foreign-repository", "GIT_WORK_TREE": "foreign-worktree",
                     "GIT_INDEX_FILE": "foreign-index", "GIT_CONFIG_COUNT": "1",
                     "PYTHONPATH": "foreign-imports", "NODE_OPTIONS": "foreign-preload",
                     "DYLD_INSERT_LIBRARIES": "foreign-library", "AWS_SECRET_ACCESS_KEY": "synthetic",
                     "OPENAI_API_KEY": "synthetic", "CODEX_HOME": "foreign-settings",
                     "HTTPS_PROXY": "foreign-proxy", "SSH_AUTH_SOCK": "foreign-agent"}
        with patch.dict(os.environ, inherited, clear=True):
            env = isolated_environment(Path("fixture-home"), Path("fixture-bin"))
            self.assertEqual(os.environ["GIT_DIR"], "foreign-repository")
        self.assertEqual(env["CODEX_HOME"], "fixture-home")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["PATH"], "fixture-bin" + os.pathsep + "known-path")
        self.assertEqual(env["LC_ALL"], "C")
        for name in inherited.keys() - {"PATH", "HOME", "LC_ALL", "CODEX_HOME"}:
            self.assertNotIn(name, env)
