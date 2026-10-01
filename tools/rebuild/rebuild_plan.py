#!/usr/bin/env python3
"""Print the rebuild-from-zero ladder and check local prerequisites, offline.

Usage:
  rebuild_plan.py              print the ladder and a prerequisite report
  rebuild_plan.py --markdown   print the runbook table (docs/runbooks/rebuild-from-zero.md)

Contacts nothing: it reads the repository and checks which tools exist and
which environment variables are SET (values are never read or printed).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LADDER = ROOT / "docs" / "runbooks" / "rebuild-ladder.yml"
LAB = ROOT / "inventory" / "lab.yml"
TOOLS = ("make", "python3", "ansible-playbook", "tofu", "ssh", "gitleaks")
ENV_NAMES = (
    "TF_VAR_proxmox_api_token",
    "TF_VAR_state_passphrase",
    "PVE_ROOT_PASSWORD_HASH",
    "PVE_ROOT_SSH_KEYS_FILE",
    "PVE_MAILTO",
)
BACKENDS = ("platform/proxmox/terraform/rebuild-guests", "services/media/terraform/arr")


def load_ladder(path: Path = LADDER) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["rungs"]


def gate_text(gate: dict) -> str:
    if "flag" in gate:
        confirmation = gate.get("confirmation")
        text = f"`{gate['flag']}`" + (f" + `{confirmation}`" if confirmation else " (flag only)")
        return text + (f" — gap: {gate['gap']}" if gate.get("gap") else "")
    return f"{gate['kind']}: {gate['reason']}"


def command(step: dict) -> str:
    if step.get("manual"):
        return "manual" + (f" (`make -C {step['component']} {step['make']}`)" if step.get("make") else "")
    return f"`make -C {step['component']} {step['make']}`"


def render_markdown(rungs: list[dict]) -> str:
    out = []
    for rung in rungs:
        out.append(f"### {rung['id']} — {rung['title']}\n")
        out.append("| Step | Command | Gate | Inputs | Duration | Verify | Rollback |")
        out.append("| --- | --- | --- | --- | --- | --- | --- |")
        notes = []
        for step in rung["steps"]:
            inputs = "; ".join(step.get("inputs") or []) or "—"
            cells = [
                f"`{step['id']}`",
                command(step),
                gate_text(step["gate"]),
                inputs,
                step["duration"],
                str(step["verify"]),
                step["rollback"],
            ]
            out.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
            if step.get("steps"):
                notes.append(f"- `{step['id']}`: {' '.join(str(step['steps']).split())}")
        if notes:
            out.append("\nOperator actions:\n")
            out.extend(notes)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def unset_lab_inputs(lab: dict) -> list[str]:
    missing = []
    for name, node in lab["nodes"].items():
        for key, value in (node.get("install") or {}).items():
            if value is None:
                missing.append(f"nodes.{name}.install.{key}")
    for name, guest in lab["guests"].items():
        if guest.get("rebuild") and guest.get("host_fingerprint") is None:
            missing.append(f"guests.{name}.host_fingerprint")
        if guest.get("onboot", False) is None:
            missing.append(f"guests.{name}.onboot")
    return missing


def report(rungs: list[dict]) -> str:
    lines = ["Rebuild ladder (one step at a time; verify before the next):", ""]
    for rung in rungs:
        lines.append(f"{rung['id']}  {rung['title']}")
        for step in rung["steps"]:
            lines.append(f"    {step['id']:<26} {command(step)}")
    lines += ["", "Local prerequisites (offline):"]
    for tool in TOOLS:
        lines.append(f"    tool {tool:<18} {'found' if shutil.which(tool) else 'MISSING'}")
    for name in ENV_NAMES:
        lines.append(f"    env  {name:<30} {'set' if os.environ.get(name) else 'unset'}")
    for root in BACKENDS:
        present = (ROOT / root / "backend.hcl").is_file()
        lines.append(f"    backend.hcl {root:<44} {'present' if present else 'missing (ADR-0003)'}")
    with LAB.open(encoding="utf-8") as fh:
        missing = unset_lab_inputs(yaml.safe_load(fh))
    lines.append(f"    lab.yml operator inputs still null: {len(missing)}")
    lines += [f"        {item}" for item in missing]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    rungs = load_ladder()
    print(render_markdown(rungs) if args.markdown else report(rungs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
