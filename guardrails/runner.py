"""Absolute-path hook entry point; use Python -I to ignore workspace imports/env."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guardrails.cli import main  # noqa: E402

raise SystemExit(main())
