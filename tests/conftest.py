"""Shared helpers for cross-component contract tests. Offline; contacts nothing."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "repo-checks"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def tracked() -> list[str]:
    import forbidden_constructs

    return forbidden_constructs.tracked_files()


@pytest.fixture(scope="session")
def guard():
    return load_module("guard", ROOT / ".claude" / "hooks" / "guard.py")
