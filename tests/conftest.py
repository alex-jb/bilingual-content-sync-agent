"""Test isolation guard.

Sets SFOS_TEST_MODE=1 so any code path calling solo_founder_os.log_outcome
/ record_example / log_edit during pytest does NOT write to the
developer's real ~/.<agent>/ dirs. Without this, fixtures that didn't
monkeypatch pathlib.Path.home() were polluting production reflexion +
example stores, which then fed false-positive proposals to the L4 evolver.

SFOS-side primitive shipped in solo-founder-os v0.20.3 (the umbrella
SFOS_TEST_MODE env var; v0.20.2 had SFOS_LOG_OUTCOME_SKIP, kept as alias).
"""
import os

os.environ.setdefault("SFOS_TEST_MODE", "1")
