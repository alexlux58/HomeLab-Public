from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GROUP_VARS = ROOT.parent / "inventory/observability/group_vars/all.yml"


class RepositoryTests(unittest.TestCase):
    def test_all_images_are_version_pinned(self) -> None:
        compose = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        images = re.findall(r"^\s+image:\s+(\S+)\s*$", compose, re.MULTILINE)
        self.assertGreaterEqual(len(images), 10)
        self.assertTrue(all(":" in image for image in images))
        self.assertFalse(any(image.endswith(":latest") for image in images))

    def test_dashboards_are_valid_json_with_stable_uids(self) -> None:
        paths = sorted((ROOT / "config/grafana/dashboards").glob("*.json"))
        self.assertGreaterEqual(len(paths), 8)
        uids = []
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["title"])
            uids.append(payload["uid"])
        self.assertEqual(len(uids), len(set(uids)))

    def test_synology_dashboard_uses_observed_exporter_schema(self) -> None:
        path = ROOT / "config/grafana/dashboards/synology.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        expressions = "\n".join(
            target.get("expr", "")
            for panel in payload["panels"]
            for target in panel.get("targets", [])
        )
        self.assertGreaterEqual(len(payload["panels"]), 18)
        for metric in (
            "raidStatus",
            "raidFreeSize",
            "diskHealthStatus",
            "diskTemperature",
            "storageIONWrittenX",
            "serviceUsers",
        ):
            self.assertIn(metric, expressions)
        self.assertNotIn("sysUpTime", expressions)
        self.assertNotIn("synology.*|hrStorage.*", expressions)

    def test_core_dashboards_have_operational_depth(self) -> None:
        minimum_panels = {
            "synology.json": 18,
            "proxmox.json": 12,
            "availability.json": 9,
            "fleet-overview.json": 11,
        }
        for filename, expected in minimum_panels.items():
            payload = json.loads(
                (ROOT / "config/grafana/dashboards" / filename).read_text(
                    encoding="utf-8"
                )
            )
            self.assertGreaterEqual(len(payload["panels"]), expected, filename)

    def test_dashboard_update_is_narrow_and_approval_gated(self) -> None:
        playbook = (ROOT / "ansible/playbooks/41-update-dashboards.yml").read_text(
            encoding="utf-8"
        )
        variables = GROUP_VARS.read_text(
            encoding="utf-8"
        )
        self.assertIn("serial: 1", playbook)
        self.assertIn("any_errors_fatal: true", playbook)
        self.assertIn("allow_observability_dashboard_update | bool", playbook)
        self.assertIn("promtool", playbook)
        self.assertIn("/-/reload", playbook)
        self.assertNotIn("docker_compose", playbook)
        self.assertIn("allow_observability_dashboard_update: false", variables)

    def test_synology_alerts_cover_health_capacity_and_temperature(self) -> None:
        rules = (ROOT / "config/prometheus/rules/synology.yml").read_text(
            encoding="utf-8"
        )
        for alert in (
            "SynologySystemUnhealthy",
            "SynologyRaidNotNormal",
            "SynologyDiskUnhealthy",
            "SynologyVolumeFilling",
            "SynologyVolumeCritical",
            "SynologyDiskTemperatureHigh",
            "SynologyDiskBadSectorsRising",
            "SynologyDiskBadSectorsHigh",
        ):
            self.assertIn(f"alert: {alert}", rules)
        self.assertIn('raidName=~"Volume .*"', rules)

    def test_bad_sector_alert_is_trend_based_not_permanently_firing(self) -> None:
        """Reallocated sectors never decrease, so `> 0` can never clear.

        A standing count must not page; only growth or an extreme absolute value
        may. Guarding this keeps the channel trustworthy.
        """
        rules = (ROOT / "config/prometheus/rules/synology.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("delta(diskBadSector", rules)
        self.assertNotIn("diskBadSector{job=\"synology-snmp\"} > 0", rules)

    def test_https_probes_use_real_npm_hostnames(self) -> None:
        http_sd = (ROOT / "config/prometheus/file_sd/http.yml").read_text(
            encoding="utf-8"
        )
        blackbox = (ROOT / "config/blackbox/blackbox.yml").read_text(encoding="utf-8")
        self.assertIn("https://home.lab.example.com/", http_sd)
        self.assertIn("https://status.lab.example.com/", http_sd)
        self.assertNotIn("homepage.lab.example.com", http_sd)
        self.assertNotIn("uptime.lab.example.com", http_sd)
        self.assertIn("query_name: home.lab.example.com", blackbox)
        self.assertNotIn("homepage.lab.example.com", blackbox)

    def test_vm300_agent_scrapes_are_empty_until_stage_ig(self) -> None:
        for name in ("node-exporter.yml", "cadvisor.yml"):
            text = (ROOT / "config/prometheus/file_sd" / name).read_text(
                encoding="utf-8"
            )
            self.assertRegex(text.strip(), r"(?m)^\[\]\s*$")
            # Comments may mention the future target; active YAML must not.
            active = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertNotIn("192.168.0.30", active)

    def test_intentional_stopped_guests_are_excluded_from_guest_down(self) -> None:
        # Assert against the parsed expression rather than the raw file text.
        # A substring check over the whole file also matches explanatory
        # comments, which made an earlier version of this test fail on a comment
        # that correctly documented why qemu/297 had been removed.
        document = yaml.safe_load(
            (ROOT / "config/prometheus/rules/proxmox.yml").read_text(encoding="utf-8")
        )
        expressions = [
            rule["expr"]
            for group in document["groups"]
            for rule in group["rules"]
            if rule.get("alert") == "ProxmoxGuestDown"
        ]
        self.assertEqual(len(expressions), 1)
        expression = expressions[0]
        # qemu/399 is the isolated restore-drill shell and is deliberately kept
        # powered off, so it must stay excluded from ProxmoxGuestDown.
        self.assertIn('id!~"qemu/399"', expression)
        # qemu/297 was destroyed on 2026-09-19. Its exclusion matched nothing and
        # described the guest as protected and merely stopped, which was false.
        # Asserting its absence stops the stale exclusion being reinstated.
        self.assertNotIn("qemu/297", expression)

    def test_dashboard_update_syncs_file_sd_and_blackbox(self) -> None:
        playbook = (ROOT / "ansible/playbooks/41-update-dashboards.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("config/prometheus/file_sd/", playbook)
        self.assertIn("config/blackbox/", playbook)
        self.assertIn("--signal=HUP", playbook)
        self.assertIn("flush_handlers", playbook)
        self.assertIn("home.lab.example.com", playbook)

    def test_no_runtime_secret_files_are_present(self) -> None:
        forbidden = {
            "snmp.yml",
            "pve.yml",
            "grafana_admin_password",
            "smtp_password",
        }
        found = [path for path in ROOT.rglob("*") if path.is_file() and path.name in forbidden]
        self.assertEqual(found, [])

    def test_retention_and_memory_limits_are_explicit(self) -> None:
        compose = (ROOT / "docker/compose.yaml").read_text(encoding="utf-8")
        loki = (ROOT / "config/loki/loki.yml").read_text(encoding="utf-8")
        self.assertIn("--storage.tsdb.retention.time=15d", compose)
        self.assertIn("--storage.tsdb.retention.size=8GB", compose)
        self.assertIn("retention_period: 168h", loki)
        self.assertGreaterEqual(compose.count("mem_limit:"), 10)

    def test_bootstrap_is_independent_and_fail_closed(self) -> None:
        bootstrap = (ROOT / "ansible/playbooks/20-bootstrap.yml").read_text(encoding="utf-8")
        common = (ROOT / "ansible/roles/common/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("serial: 1", bootstrap)
        self.assertIn("any_errors_fatal: true", bootstrap)
        self.assertIn("- role: common", bootstrap)
        self.assertIn("- role: firewall", bootstrap)
        self.assertNotIn("role: observability_stack", bootstrap)
        self.assertIn("PermitRootLogin no", common)
        self.assertIn("PasswordAuthentication no", common)
        self.assertIn("AllowTcpForwarding local", common)
        self.assertIn("Refuse an unexpected emergency swap path", common)

    def test_runtime_secrets_have_metadata_only_size_floors(self) -> None:
        variables = GROUP_VARS.read_text(encoding="utf-8")
        tasks = (ROOT / "ansible/roles/observability_stack/tasks/main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("observability_stack_minimum_secret_bytes:", variables)
        self.assertIn("grafana_admin_password: 20", variables)
        self.assertIn("smtp_password: 8", variables)
        self.assertIn("pve.yml: 80", variables)
        self.assertIn("snmp.yml: 1024", variables)
        self.assertIn("item.stat.size", tasks)
        self.assertIn("observability_stack_minimum_secret_bytes[item.item]", tasks)

    def test_deployment_restarts_docker_before_compose_and_validates_all_services(self) -> None:
        docker_tasks = (ROOT / "ansible/roles/docker/tasks/main.yml").read_text(encoding="utf-8")
        validate = (ROOT / "ansible/playbooks/90-validate.yml").read_text(encoding="utf-8")
        variables = GROUP_VARS.read_text(encoding="utf-8")
        self.assertIn("ansible.builtin.meta: flush_handlers", docker_tasks)
        self.assertIn("observability_stack_expected_services:", variables)
        self.assertIn("--status\n          - running", validate)
        self.assertIn("difference(observability_validate_running_services.stdout_lines)", validate)
        self.assertNotIn("http://127.0.0.1:", validate)
        self.assertGreaterEqual(validate.count("retries: 10"), 4)
        self.assertGreaterEqual(validate.count("delay: 3"), 4)

    def test_exporter_secret_targets_match_config_paths(self) -> None:
        compose = (ROOT / "docker/compose.yaml").read_text(encoding="utf-8")
        self.assertIn("source: pve_config\n        target: pve.yml", compose)
        self.assertIn("source: snmp_config\n        target: snmp.yml", compose)
        self.assertIn('user: "0:0"', compose)

    def test_alertmanager_root_secret_exception_is_hardened(self) -> None:
        compose = (ROOT / "docker/compose.yaml").read_text(encoding="utf-8")
        alertmanager = compose.split("  alertmanager:\n", 1)[1].split("\n  loki:\n", 1)[0]
        self.assertIn('user: "0:0"', alertmanager)
        self.assertIn("read_only: true", alertmanager)
        self.assertIn("cap_drop:\n      - ALL", alertmanager)
        self.assertIn("- smtp_password", alertmanager)
        tasks = (ROOT / "ansible/roles/observability_stack/tasks/main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'observability_stack_data_root }}/alertmanager", owner: root, group: root',
            tasks,
        )

    def test_logs_dashboard_exposes_filter_controls(self) -> None:
        payload = json.loads(
            (ROOT / "config/grafana/dashboards/logs.json").read_text(encoding="utf-8")
        )
        variables = {item["name"]: item for item in payload["templating"]["list"]}
        self.assertGreaterEqual(
            set(variables), {"host", "job", "Filters", "sev", "search", "exclude"}
        )
        self.assertEqual(variables["search"]["type"], "textbox")
        self.assertEqual(variables["exclude"]["type"], "textbox")
        self.assertEqual(variables["Filters"]["type"], "adhoc")
        expressions = "\n".join(
            target.get("expr", "")
            for panel in payload["panels"]
            for target in panel.get("targets", [])
        )
        self.assertIn('{host=~"$host", job=~"$job"}', expressions)
        self.assertNotIn('container=~"$container", unit=~"$unit"', expressions)
        self.assertIn("(?i)$search", expressions)
        self.assertTrue(any(panel.get("type") == "logs" for panel in payload["panels"]))
        self.assertTrue(any(panel.get("type") == "text" for panel in payload["panels"]))

    def test_runtime_validation_rejects_restart_loops(self) -> None:
        validate = (ROOT / "ansible/playbooks/90-validate.yml").read_text(encoding="utf-8")
        self.assertIn("community.docker.docker_container_info", validate)
        self.assertIn("item.container.State.Restarting", validate)
        self.assertIn("item.container.RestartCount", validate)
        self.assertIn("observability_stack_required_up_jobs", validate)
        self.assertIn("selectattr('health', 'equalto', 'up')", validate)


if __name__ == "__main__":
    unittest.main()
