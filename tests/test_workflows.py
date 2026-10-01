"""D7: only hosted, least-privilege checks can run on GitHub."""

import re

import pytest
import yaml

SHA_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
HOSTED = {"ubuntu-24.04"}


def load(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["on"] = doc.pop("on", doc.pop(True, None))
    return doc


def check(doc):
    assert doc["permissions"] == {}
    assert set(doc["on"]) <= {"push", "pull_request", "workflow_call"}
    assert not any(k in doc for k in ("secrets", "environment", "environments"))
    for job in doc["jobs"].values():
        assert set(job["permissions"]) <= {"contents", "pull-requests"}
        assert set(job["permissions"].values()) <= {"read", "none"}
        assert "secrets" not in job and "environment" not in job
        if "uses" in job:
            assert job["uses"] == "./.github/workflows/_component-checks.yml"
        else:
            assert job["runs-on"] in HOSTED
        for step in job.get("steps", []):
            if "uses" in step:
                assert SHA_PIN.fullmatch(step["uses"])
            run = step.get("run", "")
            assert not re.search(r"\b(?:tofu|terraform)\b[^\n]*\b(?:plan|apply|destroy|import)\b", run)
            assert not re.search(
                r"\bmake\b[^\n]*\b(?:deploy|apply|configure|bootstrap|restore|rebuild|join|create)(?:[-\w]*)\b",
                run,
            )
            assert "gated-make" not in run
            assert "-auto-approve" not in run
    assert not re.search(r"\bsecrets\s*[.\[]", yaml.safe_dump(doc))


def test_only_two_workflows_exist(root):
    files = set(p.name for p in (root / ".github/workflows").iterdir())
    assert files == {"ci.yml", "_component-checks.yml"}
    nested = [p for p in root.rglob(".github/workflows/*.y*ml") if p.parent.parent.parent != root]
    assert not [p for p in nested if not {"public", ".venv", "collections"} & set(p.parts)]


def test_all_workflows_obey_checks_only(root):
    for path in (root / ".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "pull_request_target" not in text
        assert "workflow_dispatch" not in text
        check(load(path))


@pytest.mark.parametrize(
    "bad",
    [
        {"runs-on": "self-hosted"},
        {"runs-on": ["self-hosted", "homelab"]},
        {"runs-on": "${{ inputs.runner }}"},
        {"secrets": "inherit"},
        {"environment": "production"},
        {"permissions": {"contents": "write"}},
        {"steps": [{"run": "make COMPONENT=platform/proxmox deploy"}]},
        {"steps": [{"run": "tofu -chdir=x apply plan"}]},
        {"steps": [{"run": "echo ${{ secrets.TOKEN }}"}]},
        {"steps": [{"uses": "actions/checkout@main"}]},
    ],
)
def test_rejects_unsafe_jobs(bad):
    doc = {
        "on": {"push": None},
        "permissions": {},
        "jobs": {"checks": {"runs-on": "ubuntu-24.04", "permissions": {"contents": "read"}, **bad}},
    }
    with pytest.raises((AssertionError, TypeError)):
        check(doc)


def test_workflow_linters_are_pinned_and_checksum_verified(root):
    doc = load(root / ".github/workflows/ci.yml")
    for key in ("ACTIONLINT_VERSION", "ZIZMOR_VERSION"):
        assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", doc["env"][key])
    assert re.fullmatch(r"[0-9a-f]{64}", doc["env"]["ZIZMOR_SHA256"])
    steps = doc["jobs"]["contracts"]["steps"]
    for tool in ("actionlint", "zizmor"):
        run = next(s["run"] for s in steps if s["name"].startswith(tool))
        assert "sha256sum --check" in run
    assert "--offline .github/workflows" in next(s["run"] for s in steps if s["name"].startswith("zizmor"))
