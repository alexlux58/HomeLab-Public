"""Offline fixtures for the media component. Contacts nothing."""

import sys
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMPONENT / "scripts"))


@pytest.fixture(scope="session")
def component() -> Path:
    return COMPONENT
