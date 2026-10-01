from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RepositoryTests(unittest.TestCase):
    def test_repository_safety(self) -> None:
        validator = load_script("validate_repo.py")
        self.assertEqual(validator.validate(ROOT), [])

    def test_secret_inventory_never_emits_values(self) -> None:
        scanner = load_script("secret_reference_inventory.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = "value-that-must-never-appear"
            (root / "compose.yaml").write_text(
                f"environment:\n  SMTP_PASSWORD: {value}\n", encoding="utf-8"
            )
            rendered = json.dumps(scanner.inventory(root))
            self.assertIn("SMTP_PASSWORD", rendered)
            self.assertNotIn(value, rendered)

    def test_recovery_bundle_excludes_secret_suffixes(self) -> None:
        bundler = load_script("build_recovery_bundle.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "safe.md").write_text("safe\n", encoding="utf-8")
            (root / "docs" / "private.key").write_text(
                "not included\n", encoding="utf-8"
            )
            files = [path.name for path in bundler.safe_files(root)]
            self.assertIn("safe.md", files)
            self.assertNotIn("private.key", files)

    def test_configuration_dry_run_has_no_credentials(self) -> None:
        configure = load_script("configure_openbao.py")
        actions = configure.planned_actions(ROOT, "all")
        rendered = json.dumps(actions)
        self.assertIn("snapshot-backup", rendered)
        self.assertNotIn("secret_id", rendered.lower())

    @unittest.skipUnless(
        (ROOT / "openbao/secret-hierarchy.json").is_file(),
        "excluded from the Phase 1 import; recreated in Phase 3 (see SECRETS-EXCLUDED.md)",
    )
    def test_secret_hierarchy_contains_pilot(self) -> None:
        hierarchy = json.loads((ROOT / "openbao/secret-hierarchy.json").read_text())
        self.assertIn("kv/observability/pve-exporter", hierarchy)


if __name__ == "__main__":
    unittest.main()
