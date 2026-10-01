"""Shared pytest fixtures. Everything here is offline: no host is contacted."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MONOREPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load(name):
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def fixtures_dir():
    return FIXTURES


@pytest.fixture
def discovery():
    return _load("discovery_sample.json")


@pytest.fixture
def discovery_post():
    return _load("discovery_post_sample.json")


@pytest.fixture
def protected():
    return _load("protected_guests.json")


@pytest.fixture
def manifest():
    return _load("manifest_sample.json")


@pytest.fixture
def manifest_broken():
    return _load("manifest_broken.json")


@pytest.fixture
def collisions(discovery):
    from detect_vmid_collisions import detect

    return detect(discovery, "pve1", {"pve2": {9000: 9200}}, 9200, 9999, {"pve"})
