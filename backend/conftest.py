"""Pytest fixtures shared across backend/test_*.py.

CREWAI_STORAGE_DIR must be pointed at a temp directory for any test that
touches CrewAI's own SQLite @persist() store (directly or indirectly, e.g.
via backend/registry.py's rehydration path in Step 2) — otherwise tests
would read/write the developer's real local flow_states.db under
appdirs.user_data_dir(...).

IMPORTANT — why this is set at MODULE IMPORT time, not inside a fixture:
crewai_core/flow.py's `@persist()` class decorator instantiates exactly
ONE `SQLiteFlowPersistence()` at CLASS-DECORATION time (i.e. the first time
`crewai_core.flow` is imported — see the installed
crewai/flow/persistence/decorators.py: `actual_persistence = persistence or
SQLiteFlowPersistence()`, evaluated once, outside any per-call code path).
That single instance's `db_path` is fixed forever from whatever
CREWAI_STORAGE_DIR/cwd was at THAT moment. Since Python caches module
imports, `crewai_core.flow` is only ever imported once across the whole
pytest session (via the first test module that imports `backend.registry`
or `crewai_core.flow`, directly or transitively) — a function- or even
session-scoped fixture that calls monkeypatch.setenv would run too late,
after that one-time import/decoration has already baked in the real
(un-isolated) storage path. So this env var is set here, at conftest.py's
own module import time, which pytest guarantees happens before it collects
and imports any test module in this directory.

A fresh directory (not cleaned up between tests) is used for the whole
session — good enough isolation from the developer's real local storage;
per-test isolation isn't achievable given the constraint above, so tests
that write real SQLite rows use distinct student_ids to avoid collisions
within the shared temp dir.
"""

import os
import tempfile

_STORAGE_DIR = tempfile.mkdtemp(prefix="crewai-test-storage-")
os.environ["CREWAI_STORAGE_DIR"] = _STORAGE_DIR
