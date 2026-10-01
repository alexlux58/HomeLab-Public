"""Phase 5 documentation contract: one source per document, generated tables
never stale, diagrams match their sources, and walkthrough snippets are real
lines that the build re-verifies. Offline; needs neither Pandoc nor mermaid-cli."""

import hashlib
import re
import sys

import pytest
import yaml

from conftest import ROOT, load_module

WALKTHROUGH = ROOT / "docs/walkthrough/homelab-technical-walkthrough.md"

REQUIRED_SECTIONS = [
    "Overview",
    "Repository map",
    "Safety model",
    "Proxmox cluster",
    "NAS and network",
    "Homelab services (VM 300)",
    "NetBox (VM 330)",
    "Media (workstation)",
    "Observability (VM 310)",
    "Secrets — OpenBao",
    "AAA — FreeRADIUS",
    "Rebuild ladder",
    "CI checks",
    "Backup and restore",
    "Troubleshooting",
    "Glossary",
    "Appendix A: Make targets",
    "Appendix B: Workflows",
    "Appendix C: Approval gates",
    "Appendix D: Operator inputs",
]
COMPONENT_SUBSECTIONS = ["Architecture", "Files", "Key code"]
COMPONENTS = [
    "Proxmox cluster",
    "NAS and network",
    "Homelab services (VM 300)",
    "NetBox (VM 330)",
    "Media (workstation)",
    "Observability (VM 310)",
    "Secrets — OpenBao",
]


@pytest.fixture(scope="module")
def build():
    return load_module("docs_build", ROOT / "tools/docs-build/build.py")


@pytest.fixture(scope="module")
def source():
    return WALKTHROUGH.read_text(encoding="utf-8")


def _chapters(text):
    """{chapter title: body} for level-1 headings outside code blocks."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    parts = re.split(r"^# (.+)$", text, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_docs_layout(root):
    for name in ("README.md", "architecture/README.md", "runbooks", "reference", "decisions", "walkthrough"):
        assert (root / "docs" / name).exists(), f"docs/{name} is missing"


def test_generated_reference_is_fresh():
    generator = load_module("generate_reference", ROOT / "tools/docs/generate_reference.py")
    for name, text in generator.render_all().items():
        path = ROOT / "docs/reference/generated" / name
        assert path.read_text(encoding="utf-8") == text, f"{name} is stale: run make docs-reference"


def test_diagrams_match_their_sources():
    diagrams = load_module("render_diagrams", ROOT / "tools/docs-build/render_diagrams.py")
    assert diagrams.problems() == []


def test_diagram_config_disables_html_labels(root):
    import json

    config = json.loads((root / "docs/walkthrough/diagrams/mermaid-config.json").read_text(encoding="utf-8"))
    assert config["htmlLabels"] is False
    assert config["flowchart"]["htmlLabels"] is False


def test_every_diagram_is_used_with_a_caption(root, source):
    used = set(re.findall(r'^<!-- diagram: (\S+) caption="[^"]+" -->$', source, re.M))
    sources = {p.stem for p in (root / "docs/walkthrough/diagrams").glob("*.mmd")}
    assert sources == used
    assert len(sources) >= 17


def test_walkthrough_has_every_required_section(source):
    chapters = _chapters(source)
    assert [c for c in chapters if c in REQUIRED_SECTIONS] == REQUIRED_SECTIONS
    for component in COMPONENTS:
        subsections = re.findall(r"^## (.+)$", chapters[component], re.M)
        for required in COMPONENT_SUBSECTIONS:
            assert required in subsections, f"{component}: missing ## {required}"
        assert any(s.startswith(("Operate", "Recover")) for s in subsections), component
        assert "<!-- snippet:" in chapters[component], f"{component} has no real code excerpt"


def test_destructive_stages_are_danger_callouts(source):
    assert source.count("::: danger") >= 4
    for block in re.findall(r"^::: danger\n(.*?)^:::$", source, re.M | re.S):
        assert block.strip(), "empty danger callout"


def test_snippets_and_links_resolve_and_match(build, source):
    expanded, _ = build.expand(source)
    assert "<!-- snippet:" not in expanded and "<!-- include:" not in expanded
    snippets = build.SNIPPET.findall(source)
    assert len(snippets) >= 15
    assert all(sha for _, _, _, sha, _ in snippets), "every snippet pins a hash"


def test_every_snippet_is_explained(source):
    """Each excerpt is followed by prose (2-5 sentences) before the next directive."""
    for match in re.finditer(r"^<!-- snippet: .+ -->$", source, re.M):
        after = source[match.end() :].lstrip("\n")
        paragraph = after.split("\n\n", 1)[0]
        if paragraph.startswith("<!-- snippet:"):
            continue  # consecutive excerpts share the explanation that follows them
        assert not paragraph.startswith(("<!--", "#", ":::", "```")), f"no explanation after {match.group(0)}"
        sentences = len(re.findall(r"[.!?](?:\s|$)", paragraph))
        assert 2 <= sentences <= 5, f"explanation after {match.group(0)} has {sentences} sentences"


def test_changed_source_fails_the_build(build):
    lines = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()[:3]
    good = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:12]
    build.expand(f"<!-- snippet: Makefile lines=1-3 sha={good} lang=makefile -->\n")
    with pytest.raises(build.BuildError, match="changed"):
        build.expand("<!-- snippet: Makefile lines=1-3 sha=000000000000 lang=makefile -->\n")
    with pytest.raises(build.BuildError, match="missing"):
        build.expand("<!-- snippet: no/such/file.py lines=1-3 sha=000000000000 lang=python -->\n")
    with pytest.raises(build.BuildError, match="no sha"):
        build.expand("<!-- snippet: Makefile lines=1-3 lang=makefile -->\n")
    with pytest.raises(build.BuildError, match="out of range"):
        build.expand("See [x](repo:Makefile#L1-L99999).\n")


def test_any_tool_warning_fails_the_build(build, tmp_path):
    with pytest.raises(build.BuildError, match="warned"):
        build.run([sys.executable, "-c", "import sys; sys.stderr.write('WARNING: x')"], tmp_path)
    source = (ROOT / "tools/docs-build/build.py").read_text(encoding="utf-8")
    assert "--fail-if-warnings" in source


def test_link_base_switches_between_relative_and_public(build, monkeypatch):
    monkeypatch.setenv("LINK_BASE", "local")
    assert not build.link("Makefile", 1, 3).startswith("http")
    monkeypatch.setenv("LINK_BASE", "public")
    monkeypatch.delenv("LINK_REF", raising=False)
    assert build.link("Makefile", 1, 3) == f"{build.PUBLIC_REPO}/main/Makefile#L1-L3"
    monkeypatch.setenv("LINK_REF", "0123abcd")
    assert build.link("Makefile", 1) == f"{build.PUBLIC_REPO}/0123abcd/Makefile#L1"


def test_only_listed_withheld_targets_become_plain_text(build, monkeypatch, tmp_path):
    listing = tmp_path / "withheld.txt"
    listing.write_text("MEMORY.md\n", encoding="utf-8")
    monkeypatch.setenv("LINK_WITHHELD", str(listing))
    out, _ = build.expand("See [the memory](repo:MEMORY.md) and [`x`](repo:Makefile#L1-L2).\n")
    assert "the memory (not published)" in out and "repo:" not in out
    with pytest.raises(build.BuildError, match="missing"):
        build.expand("See [gone](repo:no/such/file.md).\n")


def test_rehash_recomputes_every_pin(build):
    source = "<!-- snippet: Makefile lines=1-3 sha=000000000000 lang=makefile -->\n"
    _, rehashed = build.expand(source, fill=True, rehash=True)
    build.expand(rehashed)  # the recomputed pin now verifies
    assert "sha=000000000000" not in rehashed


def test_inline_paths_become_links_outside_code(build):
    text = "See `inventory/lab.yml`.\n\n```bash\ncat `inventory/lab.yml`\n```\n"
    out = build.autolink(text)
    assert "[`inventory/lab.yml`](repo:inventory/lab.yml)" in out
    assert "cat `inventory/lab.yml`" in out


def test_walkthrough_code_blocks_are_commands_not_copied_source(source):
    """Source code only enters through snippet directives; fences hold commands or trees."""
    for lang in re.findall(r"^```(\w*)", source, re.M)[::2]:
        assert lang in {"bash", "text"}, f"hand-written {lang or 'untyped'} block"


def test_no_document_is_a_copy(root, tracked):
    seen = {}
    for rel in sorted(p for p in tracked if p.endswith(".md") and "/legacy/" not in p):
        if (root / rel).is_symlink():
            continue  # a git symlink is how one source appears in two places
        text = (root / rel).read_text(encoding="utf-8").strip()
        if len(text) < 200:
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        assert digest not in seen, f"{rel} duplicates {seen.get(digest)}"
        seen[digest] = rel


def test_walkthrough_includes_instead_of_copying(root, source):
    included = re.findall(r"^<!-- include: (\S+)", source, re.M)
    for rel in included:
        for line in (root / rel).read_text(encoding="utf-8").splitlines():
            if len(line) > 70 and not line.startswith(("|", "<!--")):
                assert line not in source, f"text from {rel} is pasted, not included"


def test_root_makefile_has_docs_targets_and_full_check(root):
    text = (root / "Makefile").read_text(encoding="utf-8")
    for target in ("docs:", "docs-check:", "docs-reference:", "docs-diagrams:"):
        assert re.search(rf"^{target}", text, re.M)
    check = text.split("docs-check:", 1)[1].split("\n\n", 1)[0]
    for step in (
        "check_links.py",
        "generate_reference.py --check",
        "render_diagrams.py --check",
        "build.py --check",
    ):
        assert step in check


def test_ci_builds_the_pdf_with_the_devcontainer_pandoc(root):
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = ci["jobs"]["docs"]
    runs = [step.get("run", "").strip() for step in job["steps"]]
    assert "make docs-check" in runs and "make docs" in runs
    assert any("upload-artifact" in step.get("uses", "") for step in job["steps"])
    dockerfile = (root / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    assert f"ARG PANDOC_SHA256={job['env']['PANDOC_SHA256']}" in dockerfile
    assert f"ARG PANDOC_VERSION={job['env']['PANDOC_VERSION']}" in dockerfile
    assert f"ARG WEASYPRINT_VERSION={job['env']['WEASYPRINT_VERSION']}" in dockerfile


def test_link_checker_validates_repo_links():
    checker = load_module("check_links", ROOT / "tools/docs/check_links.py")
    assert checker.check_repo_link("x.md", "repo:Makefile#L1-L2") == []
    assert checker.check_repo_link("x.md", "repo:Makefile#L1-L99999")
    assert checker.check_repo_link("x.md", "repo:no/such/file")
