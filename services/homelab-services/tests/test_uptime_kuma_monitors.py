"""Uptime Kuma monitors are declared for every proxied site, and the drift
report reads the MariaDB backup dump correctly without touching VM 300."""

import gzip
import sys
from pathlib import Path

import yaml

COMPONENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COMPONENT / "scripts"))

from uptime_kuma_monitors import declared, drift, from_dump  # noqa: E402

DUMP = """-- MariaDB dump
CREATE TABLE `monitor` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(150) DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `url` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `monitor` VALUES (1,'Homepage',1,'https://home.lab.example.com/'),(2,'Old, with comma',0,NULL),(3,'It\\'s Grafana',1,'https://grafana.lab.example.com');
"""


def _dump(tmp_path):
    path = tmp_path / "uptime-kuma-all-databases.sql.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(DUMP)
    return path


def test_every_proxied_site_has_a_monitor():
    lab = yaml.safe_load((COMPONENT.parents[1] / "inventory/lab.yml").read_text(encoding="utf-8"))
    zone = lab["network"]["dns_zone"]
    urls = set(declared().values())
    for site in lab["dns_records"]["proxied"]:
        assert f"https://{site}.{zone}" in urls, site


def test_dump_parser_handles_commas_quotes_and_null(tmp_path):
    monitors = from_dump(_dump(tmp_path))
    assert monitors == {
        "Homepage": "https://home.lab.example.com/",
        "Old, with comma": "",
        "It's Grafana": "https://grafana.lab.example.com",
    }


def test_drift_report_lists_missing_undeclared_and_changed(tmp_path):
    have = from_dump(_dump(tmp_path))
    want = {"Homepage": "https://home.lab.example.com", "NetBox": "https://netbox.lab.example.com"}
    lines = drift(want, have)
    assert "missing: NetBox (https://netbox.lab.example.com)" in lines
    assert "undeclared: Old, with comma" in lines
    assert not any("Homepage" in line for line in lines), "a trailing slash is not drift"


def test_script_has_no_database_or_write_path():
    source = (COMPONENT / "scripts/uptime_kuma_monitors.py").read_text(encoding="utf-8")
    for banned in ("sqlite3", "pymysql", "mariadb.connect", "socket", "requests", "uptime_kuma_api"):
        assert banned not in source
