"""The rebuild ladder is complete, every step's target and gate are real, no
target chains rungs, and the runbook table is generated from the ladder."""

import re
import sys

import pytest
import yaml

GATE_KINDS = {"local", "manual", "read-only"}
PLACEHOLDER = re.compile(r"<[^>]+>")
INVENTORY_NAMES = {
    "pve1",
    "pve2",
    "pve",
    "homelab-services",
    "observability",
    "netbox",
    "media-vm",
    "workstation",
}


@pytest.fixture(scope="module")
def rebuild_plan(root):
    sys.path.insert(0, str(root / "tools" / "rebuild"))
    import rebuild_plan

    return rebuild_plan


@pytest.fixture(scope="module")
def rungs(rebuild_plan):
    return rebuild_plan.load_ladder()


def _steps(rungs):
    return [step for rung in rungs for step in rung["steps"]]


def _targets(makefile_text):
    """Map target -> (prerequisites, recipe lines)."""
    targets, current = {}, None
    for line in makefile_text.split("\n"):
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)\s*(.*)$", line)
        if match and not line.startswith("\t"):
            current = match.group(1)
            prereqs = match.group(2).split("##")[0].split()
            targets[current] = (prereqs, [])
        elif line.startswith("\t") and current:
            targets[current][1].append(line)
        elif line.strip() == "":
            continue
        else:
            current = None
    return targets


def test_rungs_are_l0_to_l8_in_order(rungs):
    assert [rung["id"] for rung in rungs] == [f"L{n}" for n in range(9)]


def test_every_step_is_complete(rungs):
    ids = [step["id"] for step in _steps(rungs)]
    assert len(ids) == len(set(ids)), "step ids must be unique"
    for step in _steps(rungs):
        for key in ("gate", "duration", "verify", "rollback"):
            assert step.get(key), f"{step['id']} lacks {key}"
        assert "inputs" in step, step["id"]
        if step.get("manual"):
            assert step.get("steps") or step.get("make"), f"{step['id']}: say what the operator does"
        else:
            assert step.get("component") and step.get("make"), step["id"]


def test_every_gate_is_explicit(rungs):
    for step in _steps(rungs):
        gate = step["gate"]
        if "flag" in gate:
            assert gate.get("confirmation") or gate.get("gap"), f"{step['id']}: flag without confirmation"
        else:
            assert gate.get("kind") in GATE_KINDS and gate.get("reason"), step["id"]


def test_every_make_target_exists(root, rungs):
    for step in _steps(rungs):
        if not step.get("make") or not step.get("component"):
            continue
        target = step["make"].split()[0]
        targets = _targets((root / step["component"] / "Makefile").read_text(encoding="utf-8"))
        assert target in targets, f"{step['id']}: no target {target} in {step['component']}/Makefile"


def test_no_target_chains_rungs(root, rungs):
    ladder_targets = {
        (step["component"], step["make"].split()[0]) for step in _steps(rungs) if step.get("component")
    }
    for component, target in sorted(ladder_targets):
        targets = _targets((root / component / "Makefile").read_text(encoding="utf-8"))
        prereqs, recipe = targets[target]
        others = {t for c, t in ladder_targets if c == component and t != target}
        assert not (set(prereqs) & others), f"{component}:{target} depends on another rung"
        for line in recipe:
            if "$(MAKE)" in line:
                assert not any(re.search(rf"\b{re.escape(o)}\b", line) for o in others), (
                    f"{component}:{target} invokes another rung: {line.strip()}"
                )


@pytest.fixture(scope="module")
def source_text(root, tracked):
    """Every tracked playbook, role, Terraform and inventory file, once."""
    return "\n".join(
        (root / rel).read_text(encoding="utf-8", errors="ignore")
        for rel in tracked
        if rel.endswith((".yml", ".tf", ".j2")) and not rel.startswith(("docs/", "public/", "tests/"))
    )


def test_gate_flags_and_confirmation_text_exist_in_source(rungs, source_text):
    text = source_text
    for step in _steps(rungs):
        gate = step["gate"]
        if "flag" not in gate or not step.get("component"):
            continue
        assert gate["flag"] in text, f"{step['id']}: flag {gate['flag']} is enforced nowhere"
        confirmation = gate.get("confirmation")
        if not confirmation:
            continue
        # Placeholders and inventory hostnames are filled in at run time, so
        # each literal fragment between them must appear verbatim in source.
        fragments, current = [], []
        for chunk in re.split(r"(<[^>]+>)", confirmation):
            if PLACEHOLDER.fullmatch(chunk):
                fragments.append(current)
                current = []
                continue
            for word in chunk.split():
                if word in INVENTORY_NAMES:
                    fragments.append(current)
                    current = []
                else:
                    current.append(word)
        fragments.append(current)
        for fragment in filter(None, fragments):
            assert " ".join(fragment) in text, f"{step['id']}: '{' '.join(fragment)}' not in source"


def test_runbook_table_is_generated_from_the_ladder(root, rungs, rebuild_plan):
    runbook = (root / "docs/runbooks/rebuild-from-zero.md").read_text(encoding="utf-8")
    start, end = "<!-- BEGIN GENERATED LADDER -->\n", "<!-- END GENERATED LADDER -->"
    assert start in runbook and end in runbook
    body = runbook.split(start, 1)[1].split(end, 1)[0]
    assert body == rebuild_plan.render_markdown(rungs), (
        "run: python3 tools/rebuild/rebuild_plan.py --markdown"
    )


def test_root_rebuild_plan_only_prints(root):
    targets = _targets((root / "Makefile").read_text(encoding="utf-8"))
    prereqs, recipe = targets["rebuild-plan"]
    assert prereqs == []
    assert [line.strip() for line in recipe] == ["python3 tools/rebuild/rebuild_plan.py"]
    source = (root / "tools/rebuild/rebuild_plan.py").read_text(encoding="utf-8")
    for banned in ("subprocess", "os.system", "requests", "urllib", "environ.get(name)!r"):
        assert banned not in source


def test_prerequisite_report_never_prints_env_values(rebuild_plan, monkeypatch):
    monkeypatch.setenv("TF_VAR_state_passphrase", "do-not-print-this")
    report = rebuild_plan.report(rebuild_plan.load_ladder())
    assert "do-not-print-this" not in report
    assert "TF_VAR_state_passphrase" in report and " set" in report
    assert yaml.safe_load("x: 1")  # PyYAML available in this environment
