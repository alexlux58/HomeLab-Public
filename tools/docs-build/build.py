#!/usr/bin/env python3
"""Build the technical walkthrough: Markdown -> Pandoc HTML5 -> WeasyPrint PDF.

Directives in docs/walkthrough/homelab-technical-walkthrough.md (HTML comments,
each on its own line):

  <!-- snippet: PATH lines=A-B sha=HEX12 lang=LANG -->
      Real lines A..B of PATH as a numbered, highlighted code block plus a
      source link. Fails if PATH is missing, the range is invalid, or the
      SHA-256 of those lines no longer starts with HEX12 (source changed).
  <!-- include: PATH shift=N -->
      The body of another Markdown file (single source), headings shifted by N.
  <!-- diagram: NAME caption="TEXT" -->
      docs/walkthrough/diagrams/NAME.svg as a captioned figure with a link to
      its .mmd source.

Links written as repo:PATH or repo:PATH#LA-LB become relative paths
(LINK_BASE=local, clickable when the PDF sits in the repository) or blob URLs
in the public repository at LINK_REF (LINK_BASE=public; default ref `main`,
because this private commit does not exist there). A path listed in the file
named by LINK_WITHHELD (one repository path per line; the publisher writes it)
renders as plain text marked "not published" instead of a link; any other
missing target still fails the build.

Usage:
  build.py                 build dist/homelab-technical-walkthrough.pdf
  build.py --check         validate directives and links only (no Pandoc)
  build.py --fill          add sha= to snippet directives that have none
  build.py --rehash        recompute every sha= (publisher only, on the sanitised
                           staging copy, after --check passed on the private tree)
  Environment: LINK_BASE=local|public (default local), PAPER=A4|Letter (default A4),
               LINK_REF, LINK_WITHHELD, BUILD_COMMIT and BUILD_DATE (outside Git)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WALK = ROOT / "docs" / "walkthrough"
SOURCE = WALK / "homelab-technical-walkthrough.md"
BUILD = WALK / "build"
DIST = WALK / "dist"
PDF = DIST / "homelab-technical-walkthrough.pdf"
PUBLIC_REPO = "https://github.com/alexlux58/HomeLab-Public/blob"

SNIPPET = re.compile(r"^<!-- snippet: (\S+) lines=(\d+)-(\d+)(?: sha=([0-9a-f]+))? lang=(\S+) -->$", re.M)
INCLUDE = re.compile(r"^<!-- include: (\S+)(?: shift=(\d))? -->$", re.M)
DIAGRAM = re.compile(r'^<!-- diagram: (\S+) caption="([^"]+)" -->$', re.M)
REPO_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(repo:([^)#\s]+)(?:#L(\d+)(?:-L(\d+))?)?\)")


class BuildError(Exception):
    pass


def lines_hash(path: Path, start: int, end: int) -> tuple[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if start < 1 or end < start or end > len(lines):
        raise BuildError(f"{path.relative_to(ROOT)}: lines {start}-{end} out of range (1-{len(lines)})")
    chosen = lines[start - 1 : end]
    return hashlib.sha256("\n".join(chosen).encode("utf-8")).hexdigest(), chosen


def link(rel: str, start: int | None = None, end: int | None = None) -> str:
    if not (ROOT / rel).exists():
        raise BuildError(f"link target missing: {rel}")
    if os.environ.get("LINK_BASE", "local") == "public":
        ref = os.environ.get("LINK_REF", "main")
        anchor = f"#L{start}-L{end}" if start and end else (f"#L{start}" if start else "")
        return f"{PUBLIC_REPO}/{ref}/{rel}{anchor}"
    return os.path.relpath(ROOT / rel, BUILD).replace(os.sep, "/")


FENCE = re.compile(r"^(```|~~~~).*?^\1[ \t]*$", re.M | re.S)
CODE_PATH = re.compile(r"(?<![\[`])`([A-Za-z0-9_.][\w.-]*(?:/[\w.-]+)+/?)`(?![\]`])")


def outside_fences(text: str, transform) -> str:
    """Apply transform to the text between fenced code blocks, never inside them."""
    parts, last = [], 0
    for block in FENCE.finditer(text):
        parts.append(transform(text[last : block.start()]))
        parts.append(block.group(0))
        last = block.end()
    parts.append(transform(text[last:]))
    return "".join(parts)


def autolink(text: str) -> str:
    """Link every inline-code mention of a real repository path (outside code blocks)."""

    def link_path(match: re.Match) -> str:
        rel = match.group(1).rstrip("/")
        if ".." in rel or not (ROOT / rel).exists():
            return match.group(0)
        return f"[`{match.group(1)}`](repo:{rel})"

    return outside_fences(text, lambda part: CODE_PATH.sub(link_path, part))


def withheld() -> set[str]:
    listing = os.environ.get("LINK_WITHHELD")
    if not listing:
        return set()
    lines = Path(listing).read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip()}


def expand(text: str, fill: bool = False, rehash: bool = False) -> tuple[str, str]:
    """Return (expanded markdown, source text with filled or recomputed hashes)."""
    filled = text
    hidden = withheld()

    def is_hidden(rel: str) -> bool:
        """Listed as withheld, or a directory that exists only as withheld files."""
        rel = rel.rstrip("/")
        return rel in hidden or (
            not (ROOT / rel).exists() and any(path.startswith(rel + "/") for path in hidden)
        )

    def snippet(match: re.Match) -> str:
        nonlocal filled
        rel, start, end, sha, lang = (
            match.group(1),
            int(match.group(2)),
            int(match.group(3)),
            match.group(4),
            match.group(5),
        )
        path = ROOT / rel
        if is_hidden(rel):
            return f"*Excerpt from `{rel}`, lines {start}–{end}: not published in this copy.*\n"
        if not path.is_file():
            raise BuildError(f"snippet source missing: {rel}")
        digest, chosen = lines_hash(path, start, end)
        if rehash:
            pinned = re.sub(r" sha=[0-9a-f]+", "", match.group(0)).replace(
                f" lang={lang}", f" sha={digest[:12]} lang={lang}"
            )
            filled = filled.replace(match.group(0), pinned, 1)
        elif sha is None:
            if not fill:
                raise BuildError(f"snippet {rel}:{start}-{end} has no sha= (run build.py --fill)")
            filled = filled.replace(
                match.group(0), match.group(0).replace(f" lang={lang}", f" sha={digest[:12]} lang={lang}"), 1
            )
        elif not digest.startswith(sha):
            raise BuildError(
                f"snippet {rel}:{start}-{end} changed (sha {sha} != {digest[:12]}); review and update"
            )
        body = "\n".join(chosen)
        fence = "~~~~" if "```" in body else "```"
        return (
            f'{fence} {{.{lang} .numberLines startFrom="{start}"}}\n{body}\n{fence}\n\n'
            f"*Source: [{rel}, lines {start}–{end}](repo:{rel}#L{start}-L{end})*\n"
        )

    def include(match: re.Match) -> str:
        rel, shift = match.group(1), int(match.group(2) or 0)
        path = ROOT / rel
        if not path.is_file():
            raise BuildError(f"include missing: {rel}")
        body = re.sub(r"^<!--.*?-->\n+", "", path.read_text(encoding="utf-8"), flags=re.S)
        heading = re.compile(r"^(#+) ", re.M)
        body = outside_fences(
            body, lambda part: heading.sub(lambda m: "#" * min(6, len(m.group(1)) + shift) + " ", part)
        )

        def relink(link_match: re.Match) -> str:
            target = link_match.group(1).split("#", 1)[0]
            resolved = (path.parent / target).resolve().relative_to(ROOT).as_posix()
            return f"](repo:{resolved})"

        # Relative links in the included file resolve against that file, not the build.
        body = outside_fences(
            body, lambda part: re.sub(r"\]\((?!https?:|mailto:|#|repo:)([^)\s]+)\)", relink, part)
        )
        return body.strip() + f"\n\n*Source: [{rel}](repo:{rel})*\n"

    def diagram(match: re.Match) -> str:
        name, caption = match.group(1), match.group(2)
        svg = WALK / "diagrams" / f"{name}.svg"
        if not svg.is_file():
            raise BuildError(f"diagram missing: {svg.relative_to(ROOT)} (run make docs-diagrams)")
        rel_svg = os.path.relpath(svg, BUILD).replace(os.sep, "/")
        return (
            f"![{caption}]({rel_svg})\n\n"
            f"*Diagram source: [docs/walkthrough/diagrams/{name}.mmd](repo:docs/walkthrough/diagrams/{name}.mmd)*\n"
        )

    out = INCLUDE.sub(include, text)
    out = SNIPPET.sub(snippet, out)
    out = DIAGRAM.sub(diagram, out)
    out = autolink(out)

    def repo_link(match: re.Match) -> str:
        label, rel, start, end = match.group(1), match.group(2), match.group(3), match.group(4)
        if is_hidden(rel):
            return f"{label} (not published)"
        start_i = int(start) if start else None
        end_i = int(end) if end else None
        if start_i:
            lines_hash(ROOT / rel, start_i, end_i or start_i)  # the lines must exist
        return f"[{label}]({link(rel, start_i, end_i)})"

    out = REPO_LINK.sub(repo_link, out)
    return out, filled


def paper_css() -> str:
    paper = os.environ.get("PAPER", "A4")
    if paper not in {"A4", "Letter"}:
        raise BuildError("PAPER must be A4 or Letter")
    return f"@page {{ size: {paper}; }}\n"


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    noise = [line for line in (result.stderr + result.stdout).splitlines() if line.strip()]
    if result.returncode != 0 or noise:
        raise BuildError(f"{cmd[0]} failed or warned:\n" + "\n".join(noise[-40:]))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def check_rendered(html: str) -> None:
    """Every in-document anchor resolves; no stray relative link escapes repo: handling."""
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    missing = sorted({h for h in re.findall(r'href="#([^"]+)"', html) if h not in ids})
    if missing:
        raise BuildError("broken anchors: " + ", ".join(missing))
    for href in re.findall(r'href="([^"#][^"]*)"', html):
        if href.startswith(("https://", "mailto:")):
            continue
        target = (BUILD / href.split("#", 1)[0]).resolve()
        if not target.exists():
            raise BuildError(f"broken link: {href}")


def build() -> Path:
    expanded, _ = expand(SOURCE.read_text(encoding="utf-8"))
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    (BUILD / "walkthrough.md").write_text(expanded, encoding="utf-8")
    (BUILD / "paper.css").write_text(paper_css(), encoding="utf-8")
    shutil.copy(HERE / "print.css", BUILD / "print.css")
    run(
        [
            "pandoc",
            "walkthrough.md",
            "--from=markdown",
            "--to=html5",
            "--standalone",
            f"--template={HERE / 'template.html'}",
            f"--metadata-file={HERE / 'metadata.yaml'}",
            f"--metadata=commit:{os.environ.get('BUILD_COMMIT') or git('rev-parse', '--short=12', 'HEAD')}",
            f"--metadata=date:{os.environ.get('BUILD_DATE') or git('show', '-s', '--format=%cs', 'HEAD')}",
            f"--metadata=paper:{os.environ.get('PAPER', 'A4')}",
            f"--metadata=linkbase:{os.environ.get('LINK_BASE', 'local')}",
            "--toc",
            "--toc-depth=2",
            "--number-sections",
            "--syntax-highlighting=tango",
            "--css=print.css",
            "--css=paper.css",
            "--fail-if-warnings",
            "--output=walkthrough.html",
        ],
        BUILD,
    )
    check_rendered((BUILD / "walkthrough.html").read_text(encoding="utf-8"))
    run(["weasyprint", "--pdf-variant=pdf/ua-1", "walkthrough.html", str(PDF)], BUILD)
    return PDF


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--fill", action="store_true")
    group.add_argument("--rehash", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.fill or args.rehash:
            _, filled = expand(SOURCE.read_text(encoding="utf-8"), fill=True, rehash=args.rehash)
            SOURCE.write_text(filled, encoding="utf-8", newline="\n")
            print("recomputed every snippet hash" if args.rehash else "filled missing snippet hashes")
        elif args.check:
            expand(SOURCE.read_text(encoding="utf-8"))
            print("walkthrough directives and links are valid")
        else:
            print(f"built {build().relative_to(ROOT)}")
    except BuildError as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
