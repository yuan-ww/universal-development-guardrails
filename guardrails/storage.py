"""Private, allowlisted audit records and opt-in optimistic file revisions."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .policy import Invalid


def audit(directory: Path, platform: str, kind: str, decision, response: str):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise Invalid("audit_symlink")
    path = directory / "decisions.sqlite3"
    if path.is_symlink():
        raise Invalid("audit_symlink")
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    os.close(fd)
    # SQLite serializes concurrent writers. No raw inputs, output, paths,
    # environment, session ids, hashes of secrets, or exception strings retained.
    record = {"version": 1, "time": datetime.now(timezone.utc).isoformat(),
              "platform": platform, "kind": kind, "mode": decision.mode,
              "policy_decision": decision.policy_decision,
              "effective_decision": decision.effective_decision,
              "policy_ids": decision.policy_ids, "host_response": response}
    # sqlite3.Connection.__exit__ commits/rolls back but does NOT close.
    # Explicit closure also releases Windows file handles before returning.
    with closing(sqlite3.connect(path, timeout=1)) as db, db:
        # Serialize schema creation and insert in one write transaction, avoiding
        # concurrent deferred schema/read-to-write upgrades. Keep the same bounded
        # busy timeout; contention may still fail and must follow the mode policy.
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS decisions (record TEXT NOT NULL)")
        db.execute("INSERT INTO decisions VALUES (?)", (json.dumps(record),))


def revision(path: Path) -> str:
    """Compare immediately before a cooperative edit; this is NOT a file lock.

    Agents sharing a sandbox can bypass this helper or race after comparison.
    Prefer isolated worktrees and host-native CAS edits for real coordination.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_revision(path: Path, expected: str) -> bool:
    return revision(path) == expected
