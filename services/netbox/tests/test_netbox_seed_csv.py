"""NetBox seed data comes only from lab.yml and covers every identity."""

import csv
import io
import sys
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMPONENT / "scripts"))

import netbox_seed_csv as seed  # noqa: E402


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_every_placed_guest_and_node_is_seeded():
    lab = seed.load()
    vms = {row["name"] for row in _rows(seed.to_csv(seed.virtual_machines(lab)))}
    assert {name for name, g in lab["guests"].items() if g.get("node")} == vms
    devices = {row["name"] for row in _rows(seed.to_csv(seed.devices(lab)))}
    assert set(lab["nodes"]) | {lab["nas"]["name"]} == devices


def test_every_address_is_seeded_once():
    lab = seed.load()
    addresses = [row["address"] for row in _rows(seed.to_csv(seed.ip_addresses(lab)))]
    assert len(addresses) == len(set(addresses))
    assert "192.168.0.50/24" in addresses and "192.168.0.11/24" in addresses


def test_seed_contains_no_secret_or_fingerprint():
    lab = seed.load()
    text = "".join(
        seed.to_csv(rows) for rows in (seed.devices(lab), seed.virtual_machines(lab), seed.ip_addresses(lab))
    )
    assert "SHA256:" not in text and "ssh-" not in text


def test_script_never_calls_the_netbox_api():
    source = (COMPONENT / "scripts/netbox_seed_csv.py").read_text(encoding="utf-8")
    for banned in ("requests", "urllib", "pynetbox", "http.client"):
        assert banned not in source
