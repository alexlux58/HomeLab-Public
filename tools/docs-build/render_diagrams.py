#!/usr/bin/env python3
"""Render docs/walkthrough/diagrams/*.mmd to .svg with mermaid-cli.

Uses the shared mermaid-config.json (htmlLabels false, one theme). Fails if an
SVG contains <foreignObject>, which WeasyPrint does not render. Records the
SHA-256 of every source plus the config in manifest.json so a test can prove
the committed SVGs match their sources.

Usage: render_diagrams.py            render every diagram (needs mmdc)
       render_diagrams.py --check    only verify manifest, SVGs and labels
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DIAGRAMS = Path(__file__).resolve().parents[2] / "docs" / "walkthrough" / "diagrams"
CONFIG = DIAGRAMS / "mermaid-config.json"
MANIFEST = DIAGRAMS / "manifest.json"
PUPPETEER = Path("/etc/puppeteer-config.json")


def source_hash(mmd: Path) -> str:
    digest = hashlib.sha256()
    digest.update(mmd.read_bytes())
    digest.update(CONFIG.read_bytes())
    return digest.hexdigest()


def problems() -> list[str]:
    found = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    for mmd in sources:
        svg = mmd.with_suffix(".svg")
        if not svg.is_file():
            found.append(f"{svg.name}: missing; run make docs-diagrams")
            continue
        if manifest.get(mmd.name) != source_hash(mmd):
            found.append(f"{mmd.name}: source changed since its SVG was rendered")
        if "<foreignObject" in svg.read_text(encoding="utf-8"):
            found.append(f"{svg.name}: contains <foreignObject> (WeasyPrint drops it)")
    stale = set(manifest) - {m.name for m in sources}
    found += [f"{name}: in manifest but the source is gone" for name in sorted(stale)]
    return found


def render() -> None:
    manifest = {}
    for mmd in sorted(DIAGRAMS.glob("*.mmd")):
        svg = mmd.with_suffix(".svg")
        cmd = ["mmdc", "-c", str(CONFIG), "-i", str(mmd), "-o", str(svg), "-b", "white", "--quiet"]
        if PUPPETEER.is_file():
            cmd[1:1] = ["-p", str(PUPPETEER)]
        subprocess.run(cmd, check=True)
        manifest[mmd.name] = source_hash(mmd)
        print(f"rendered {svg.name}")
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.check:
        render()
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
