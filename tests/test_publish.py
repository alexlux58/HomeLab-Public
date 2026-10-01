"""Phase 6 publisher contract: default-deny selection, a scanner that sees
inside PDFs and SVGs, patterns for Plex/*arr/DDNS values, and a publisher that
never commits or pushes. Offline. Sample values are assembled at runtime so
this file itself stays clean for both scanners."""

import re
import shutil
import subprocess
import sys
import zlib

import pytest

from conftest import ROOT, load_module

sys.path.insert(0, str(ROOT / "tools" / "publish"))
scan = load_module("scan_public", ROOT / "tools/publish/scan_public.py")
publish = load_module("publish_snapshot", ROOT / "tools/publish/publish_snapshot.py")

PUBLIC_REPO = "https://github.com/" + "labadmin/HomeLab-Public"
OWNER = PUBLIC_REPO.split("/")[3]
HEX32 = "0123456789abcdef" * 2
HEX40 = HEX32 + "01234567"


@pytest.fixture(scope="module")
def policy():
    return publish.load_policy()


@pytest.fixture(scope="module")
def classified(policy, tracked):
    return publish.classify(tracked, policy)


# --------------------------------------------------------------------------- policy
@pytest.mark.parametrize(
    "rel",
    [
        "MEMORY.md",
        "CLAUDE.md",
        "HOMELAB-ROADMAP.md",
        "README.md",
        "tools/publish/sanitize-for-public.sh",
        "tools/publish/policy.yml",
        ".github/workflows/ci.yml",
        "docs/_plan/00-media-ledger.md",
        "docs/reference/environment.md",
        "docs/reference/legacy/HANDOFF-PROMPT.md",
        "docs/walkthrough/legacy/HOMELAB-TECHNICAL-WALKTHROUGH.pdf",
        "platform/proxmox/host-configs/pve1/x.conf",
        "platform/proxmox/artifacts/preflight.json",
        "platform/proxmox/tests/fixtures/discovery.json",
        "platform/proxmox/site/devices.json",
        "services/music-library/README.md",
        "security/aaa-freeradius/docs/aaa-deployment.md",
        ".claude/skills/build-docs",
        ".runtime/radarr/config/config.xml",
        "observability/.gitignore",
    ],
)
def test_sensitive_paths_are_never_published(policy, rel):
    published, withheld = publish.classify([rel], policy)
    assert not published and withheld[rel]


@pytest.mark.parametrize(
    "rel",
    [
        "AGENTS.md",
        "inventory/lab.yml",
        "platform/proxmox/Makefile",
        "services/media/config/compose.yaml",
        "observability/scripts/backup.sh",
        "tests/test_docs.py",
        "docs/walkthrough/homelab-technical-walkthrough.md",
        "docs/walkthrough/diagrams/05-gated-stage.mmd",
        "security/aaa-freeradius/ansible/playbooks/00-preflight.yml",
    ],
)
def test_reviewed_paths_are_published(policy, rel):
    published, _ = publish.classify([rel], policy)
    assert published == [rel]


def test_every_rule_is_live_and_explained(policy, tracked):
    for glob in policy["publish"]:
        assert any(publish.matches(rel, glob) for rel in tracked), f"publish glob {glob} matches nothing"
    for rule in policy["withhold"]:
        assert len(rule["reason"]) > 20, f"{rule['glob']} needs a real reason"
    published, _ = publish.classify(tracked, policy)
    assert set(policy["verbatim"]) <= set(published)


def test_walkthrough_inputs_are_published_or_explicitly_withheld(classified, root):
    published, withheld = classified
    source = (root / "docs/walkthrough/homelab-technical-walkthrough.md").read_text(encoding="utf-8")
    for rel in re.findall(r"^<!-- include: (\S+)", source, re.M):
        assert rel in published, f"included {rel} must be published"
    for name in re.findall(r"^<!-- diagram: (\S+)", source, re.M):
        assert f"docs/walkthrough/diagrams/{name}.mmd" in published
    for rel in re.findall(r"^<!-- snippet: (\S+)", source, re.M):
        assert rel in published or rel in withheld


def test_overlay_supplies_the_public_readme_and_the_aaa_stub(root):
    overlay = root / "tools/publish/overlay"
    assert (overlay / "README.md").is_file() and (overlay / ".gitignore").is_file()
    stub = (overlay / "security/aaa-freeradius/docs/aaa-deployment.md").read_text(encoding="utf-8")
    assert "not copied into" in stub and len(stub) < 600


# --------------------------------------------------------------------------- patterns
SAMPLES = {
    "private IPv4": ".".join(["10", "9", "8", "7"]),
    "partial IPv4": ".".join(["172", "20", "1", "x"]),
    "MAC address": ":".join(["AA", "BB", "CC", "11", "22", "33"]),
    "SSH fingerprint": "SHA" + "256:" + "Q" * 43,
    "private key": "BEGIN OPENSSH " + "PRIVATE KEY",
    "email address": "someone" + "@" + "mail.test.org",
    "AWS-style key": "AKIA" + "Q" * 16,
    "API token": "gh" + "p_" + "a" * 36,
    "Plex token": "X-Plex-" + "Token=" + "Ab1_" * 5,
    "Plex machine identifier": "machine" + 'Identifier="' + HEX40 + '"',
    "Plex server id in URL": "https://app." + "plex.tv/desktop/#!/server/" + HEX40,
    "*arr API key": "<Api" + "Key>" + HEX32 + "</ApiKey>",
    "DDNS hostname": "home-lab." + "duck" + "dns.org",
}


def test_every_pattern_has_a_sample():
    assert set(SAMPLES) == set(scan.PATTERNS)


@pytest.mark.parametrize("label", sorted(SAMPLES))
def test_pattern_catches_its_sample(label):
    findings = scan.scan_text("f.md", "text", f"value: {SAMPLES[label]}\n", [], [])
    assert any(label in f for f in findings), findings


@pytest.mark.parametrize(
    "text",
    [
        "HEX variable names only: X-Plex-Token, api_key, machineIdentifier",
        "placeholder 192.168.0.11/24 and 52:54:00:00:00:00",
        "SHA256:EXAMPLE_FINGERPRINT_REDACTED alerts@example.com",
        "the DDNS name example.duckdns.org is a documentation placeholder",
    ],
)
def test_placeholders_and_names_are_not_findings(text):
    assert scan.scan_text("f.md", "text", text, [], []) == []


def test_secret_values_are_masked_in_the_report():
    (finding,) = scan.scan_text("f.md", "text", SAMPLES["*arr API key"], [], [])
    assert HEX32 not in finding


def test_only_the_public_repository_url_escapes_the_literal_denylist():
    assert scan.scan_text("f.md", "text", f"see {PUBLIC_REPO}/blob/main/x", [OWNER], []) == []
    bare = PUBLIC_REPO.removeprefix("https://")
    assert scan.scan_text("f.md", "text", f"(public/ -> {bare})", [OWNER], []) == []
    assert scan.scan_text("f.md", "text", f"user {OWNER} on host", [OWNER], [])
    for other in ("homelab", "HomeLab", "HomeLab-Private", "HomeLab-Public-extra", "homelab-public"):
        url = f"https://github.com/{OWNER}/{other}"
        assert scan.scan_text("f.md", "text", url, [OWNER], [])


# --------------------------------------------------------------------------- extraction
def test_svg_values_split_across_tspans_are_reassembled(tmp_path):
    svg = tmp_path / "d.svg"
    parts = SAMPLES["private IPv4"].split(".")
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>'
        f"<tspan>{parts[0]}.{parts[1]}</tspan><tspan>&#46;{parts[2]}.{parts[3]}</tspan>"
        "</text></svg>",
        encoding="utf-8",
    )
    findings = scan.scan_files(tmp_path, [svg], [], [])
    assert any("[svg text] private IPv4" in f for f in findings), findings
    assert not any("[svg] private IPv4" in f for f in findings)


def _pdf(tmp_path, payload: bytes):
    body = zlib.compress(payload)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(
        b"%PDF-1.7\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + body + b"\nendstream\nendobj\n%%EOF\n"
    )
    return pdf


def test_pdf_link_uris_inside_compressed_streams_are_scanned(tmp_path):
    uri = f"https://{SAMPLES['DDNS hostname']}/x".encode()
    pdf = _pdf(tmp_path, b"<< /S /URI /URI (" + uri + b") >>")
    assert uri not in pdf.read_bytes()  # grep on the file could not see it
    findings = scan.scan_text("doc.pdf", "pdf streams", scan.pdf_streams(pdf.read_bytes()), [], [])
    assert any("DDNS hostname" in f for f in findings), findings


def _font(name, glyph_bytes):
    """SFNT name table plus a binary outline table, like a subset PDF font."""
    import struct

    value = name.encode("utf-16-be")
    names = struct.pack(">HHH", 0, 1, 18) + struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(value), 0) + value
    header = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 2, 0, 0, 0)
    tables = struct.pack(">4sIII", b"name", 0, 44, len(names))
    tables += struct.pack(">4sIII", b"glyf", 0, 44 + len(names), len(glyph_bytes))
    return header + tables + names + glyph_bytes


def test_pdf_font_binary_is_not_an_invented_email(tmp_path):
    noise = b"\x00\xffX" + b"@" + b"e1.XD\x01"
    pdf = _pdf(tmp_path, _font("Test Font", noise))
    text = scan.pdf_streams(pdf.read_bytes())
    assert "Test Font" in text
    assert scan.scan_text("doc.pdf", "pdf streams", text, [], []) == []


def test_pdf_font_metadata_still_gets_secret_and_denylist_scans(tmp_path):
    name = SAMPLES["email address"] + " " + SAMPLES["DDNS hostname"] + " " + SAMPLES["private key"]
    pdf = _pdf(tmp_path, _font(name, b"\x00\xff"))
    findings = scan.scan_text("doc.pdf", "pdf streams", scan.pdf_streams(pdf.read_bytes()), [name], [])
    assert any("DENYLIST" in finding for finding in findings)
    assert any("email address" in finding for finding in findings)
    assert any("DDNS hostname" in finding for finding in findings)
    assert any("private key" in finding for finding in findings)


def test_pdf_malformed_font_and_unterminated_stream_fail_closed(tmp_path):
    for payload in (b"\x00\x01\x00\x00", _font("Font", b"\x00")[:30]):
        pdf = _pdf(tmp_path, payload)
        with pytest.raises(scan.ExtractionError, match="font"):
            scan.pdf_streams(pdf.read_bytes())
    with pytest.raises(scan.ExtractionError, match="unterminated"):
        scan.pdf_streams(b"%PDF-1.7\nstream\nsomething")


def test_pdf_broken_flate_stream_fails_closed():
    with pytest.raises(scan.ExtractionError, match="decompress"):
        scan.pdf_streams(b"%PDF-1.7\n<< /Filter /FlateDecode >>\nstream\nbroken\nendstream\n")


def test_a_pdf_without_a_text_extractor_fails_closed(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path, b"nothing")
    monkeypatch.setattr(scan.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "pypdf", None)
    (finding,) = scan.scan_files(tmp_path, [pdf], [], [])
    assert finding.startswith("UNSCANNED") and "extractor" in finding


def test_an_unknown_binary_fails_closed(tmp_path):
    blob = tmp_path / "image.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0")
    (finding,) = scan.scan_files(tmp_path, [blob], [], [])
    assert finding.startswith("UNSCANNED")


def test_scanner_refuses_a_missing_tree_or_denylist(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "DENYLIST", tmp_path / "absent")
    assert scan.main([str(tmp_path)]) == 2
    listing = tmp_path / "deny"
    listing.write_text("x-not-present\n", encoding="utf-8")
    monkeypatch.setattr(scan, "DENYLIST", listing)
    assert scan.main([str(tmp_path / "empty")]) == 2


# --------------------------------------------------------------------------- publisher
def test_publisher_never_commits_or_pushes(root):
    for name in ("publish_snapshot.py", "scan_public.py", "check-public.sh", "sanitize-for-public.sh"):
        text = (root / "tools/publish" / name).read_text(encoding="utf-8")
        assert not re.search(r"""["'\s](push|commit)["'\s]*[,\]]""", text), name
        assert "--force" not in text


def test_publisher_scans_before_touching_public_and_refuses_a_dirty_tree(root):
    text = (root / "tools/publish/publish_snapshot.py").read_text(encoding="utf-8")
    main = text.split("def main", 1)[1]
    assert main.index("scan_files") < main.index("replace_public(")
    assert "uncommitted changes" in text and '"--porcelain"' in text
    assert "rm -rf" not in text


def test_staged_text_is_normalised_to_lf_and_binaries_are_untouched(tmp_path):
    text, blob = tmp_path / "a.yml", tmp_path / "b.bin"
    text.write_bytes(b"a: 1\r\nb: 2\r\n")
    blob.write_bytes(b"\0\r\n\0")
    publish.normalise_line_endings(tmp_path)
    assert text.read_bytes() == b"a: 1\nb: 2\n"
    assert blob.read_bytes() == b"\0\r\n\0"


def test_check_public_wrapper_keeps_the_hook_path_and_fails_closed(root):
    text = (root / "tools/publish/check-public.sh").read_text(encoding="utf-8")
    assert "scan_public.py" in text and "exit 2" in text
    assert not (root / "tools/publish/publish-snapshot.sh").exists()


@pytest.mark.skipif(not shutil.which("perl"), reason="perl is needed to run the sanitiser")
def test_sanitiser_keeps_the_public_url_and_masks_new_identities(tmp_path, root):
    source = tmp_path / "in.md"
    source.write_text(
        f"{PUBLIC_REPO}/blob/main/x\nowner {OWNER}\nC:\\Users\\{'labuser' + 'l'}\\Documents\n"
        f"guest {'LUX' + '-MEDIA-VM'}\n"
        f"unlisted {'192.168.' + '5.99'} and {'192.168.' + '4.254'}\n",
        encoding="utf-8",
    )
    dest = tmp_path / "out.md"
    subprocess.run(
        ["bash", str(root / "tools/publish/sanitize-for-public.sh"), str(source), str(dest)], check=True
    )
    out = dest.read_text(encoding="utf-8")
    assert f"{PUBLIC_REPO}/blob/main/x" in out
    assert f"owner {OWNER}" not in out and "owner labadmin" in out
    assert "Users\\labuser\\" in out and "media-vm" in out
    assert "unlisted 198.51.100.99 and 198.51.100.254" in out
    assert scan.scan_text("out.md", "text", out, [], []) == []
