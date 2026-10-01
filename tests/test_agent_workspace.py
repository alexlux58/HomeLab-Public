"""The agent workspace stays in the shape Phase 2 set up: short tool-neutral
AGENTS.md files, CLAUDE.md files that only import them, one copy of each skill
linked into Claude Code, and a volatile-only MEMORY.md."""

import os
import re

import pytest

COMPONENTS = [
    "platform/proxmox",
    "platform/nas",
    "observability",
    "security/secrets-openbao",
    "security/aaa-freeradius",
    "services/homelab-services",
    "services/netbox",
    "services/media",
    "tools/publish",
    "tests",
]

SKILLS = [
    "add-homelab-service",
    "add-media-app",
    "add-gated-playbook",
    "add-opentofu-resource",
    "run-gated-stage",
    "rebuild-from-zero",
    "ci-failure-triage",
    "build-docs",
    "publish-sanitised",
    "triage-safety-test-failure",
]

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _frontmatter(text):
    match = FRONTMATTER.match(text)
    assert match, "missing YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


@pytest.mark.parametrize("component", ["", *COMPONENTS])
def test_every_component_has_a_short_agents_md(root, component):
    path = root / component / "AGENTS.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 150, f"{path} has {len(lines)} lines"
    if component:
        assert "Inherits `" in "\n".join(lines[:6]), "component rules must inherit the root"


@pytest.mark.parametrize("component", COMPONENTS)
def test_component_claude_md_only_imports_agents_md(root, component):
    text = (root / component / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in text
    assert len(text.splitlines()) <= 8, "rules belong in AGENTS.md, not CLAUDE.md"


def test_root_claude_md_imports_the_shared_context(root):
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    for target in (
        "@AGENTS.md",
        "@MEMORY.md",
        "@docs/reference/environment.md",
        "@docs/reference/lessons-learned.md",
    ):
        assert target in text
        assert (root / target[1:]).is_file()
    assert len(text.splitlines()) <= 40


def test_memory_md_has_the_volatile_sections(root):
    text = (root / "MEMORY.md").read_text(encoding="utf-8")
    for heading in (
        "## Current state",
        "## Dated decisions",
        "## Known gaps",
        "## Rotation list",
        "## Next steps",
    ):
        assert heading in text
    assert "workstation" in text


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_has_trigger_description_and_resolving_links(root, skill):
    text = (root / ".agents/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    fields = _frontmatter(text)
    assert fields.get("name") == skill
    assert len(fields.get("description", "")) >= 60, "description must say when to trigger"
    assert fields["description"].startswith("Use when")
    for ref in re.findall(
        r"`((?:platform|services|security|observability|inventory|tools|docs|tests)/[^`\s<>*]+)`", text
    ):
        assert (root / ref.rstrip("/")).exists(), f"{skill} links to missing {ref}"


def test_every_skill_is_listed_in_agents_md_and_nothing_else(root):
    on_disk = {p.name for p in (root / ".agents/skills").iterdir() if p.is_dir()}
    assert on_disk == set(SKILLS)
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for skill in SKILLS:
        assert f"`{skill}`" in agents


@pytest.mark.parametrize("skill", SKILLS)
def test_claude_skill_entry_links_to_the_single_copy(root, skill):
    """A git symlink. With core.symlinks=false it checks out as a text file
    holding the target, which is accepted here but does not load."""
    entry = root / ".claude/skills" / skill
    expected = f"../../.agents/skills/{skill}"
    if entry.is_symlink():
        assert os.readlink(entry).replace("\\", "/") == expected
        assert (entry / "SKILL.md").is_file()
    else:
        assert entry.is_file(), f"{entry} missing"
        assert entry.read_text(encoding="utf-8").strip() == expected


def test_safety_reviewer_prompt_exists_and_is_linked(root):
    path = root / ".agents/agents/safety-reviewer.md"
    fields = _frontmatter(path.read_text(encoding="utf-8"))
    assert fields.get("name") == "safety-reviewer"
    assert fields.get("description")
    entry = root / ".claude/agents/safety-reviewer.md"
    expected = "../../.agents/agents/safety-reviewer.md"
    if entry.is_symlink():
        assert os.readlink(entry).replace("\\", "/") == expected
    else:
        assert entry.read_text(encoding="utf-8").strip() == expected
