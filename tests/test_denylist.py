"""No secret-bearing file or secret-shaped value is tracked, anywhere."""

import re
from pathlib import PurePosixPath

import pytest

DENIED_PATHS = re.compile(
    r"""(?ix)
    \.tfstate(\.|$)
    | (^|/)[^/]*\.env$
    | (^|/)\.env\.(?!example$)[^/]+$
    | \.tfvars(\.json)?$
    | \.(pem|key|p12|pfx|kdbx)$
    | (^|/)id_(rsa|ed25519|ecdsa|dsa)$
    | _ed25519$
    | (^|/)Preferences\.xml$
    | (^|/)config\.xml$
    | (^|/)auth\.json$
    | (^|/)\.runtime/
    """
)
# Placeholder directories are tracked on purpose; nothing else inside them.
KEEP_ONLY = re.compile(r"(^|/)(artifacts|host-configs)/")

DENIED_CONTENT = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    "OpenBao/Vault token": re.compile(r"\bhvs\.[A-Za-z0-9_-]{24,}"),
    "Plex token": re.compile(r"X-Plex-Token[=:\"' ]+[A-Za-z0-9_-]{18,}|PlexOnlineToken=\"[^\"]{8,}"),
    "*arr API key": re.compile(r"<ApiKey>[0-9a-f]{32}</ApiKey>"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zst", ".gz", ".ico", ".woff", ".woff2"}


def test_no_secret_bearing_path_is_tracked(tracked):
    bad = [p for p in tracked if DENIED_PATHS.search(p)]
    bad += [p for p in tracked if KEEP_ONLY.search(p) and PurePosixPath(p).name != ".gitkeep"]
    assert not bad, bad


@pytest.mark.parametrize("label", sorted(DENIED_CONTENT))
def test_no_secret_shaped_value_is_tracked(root, tracked, label):
    pattern = DENIED_CONTENT[label]
    hits = []
    for rel in tracked:
        if PurePosixPath(rel).suffix.lower() in BINARY or rel == "tests/test_denylist.py":
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(text):
            hits.append(rel)
    assert not hits, f"{label} found in {hits}"


def test_denylist_patterns_catch_samples():
    assert DENIED_PATHS.search("platform/x/terraform.tfstate.backup")
    assert DENIED_PATHS.search("services/media/.env")
    assert not DENIED_PATHS.search("services/media/.env.example")
    assert DENIED_CONTENT["*arr API key"].search("<ApiKey>" + "0" * 32 + "</ApiKey>")
    assert DENIED_CONTENT["private key"].search("-----BEGIN OPENSSH " + "PRIVATE KEY-----")
