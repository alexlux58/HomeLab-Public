#!/usr/bin/env python3
"""Declare Plex libraries from config/plex/libraries.yml (python-plexapi).

Modes:
  plan (default)  read-only: show what --apply would add and any setting drift
  check           read-only: Plex answers and reports its version
  --apply         add missing libraries; needs PLEX_ALLOW_APPLY=true and
                  PLEX_CONFIRMATION="PLEX LIBRARIES <server>" (server from the YAML)

Environment: PLEX_URL (default http://127.0.0.1:32400), PLEX_TOKEN (operator
input; never printed). Existing libraries and server settings are never
modified or deleted: drift is reported for the operator to resolve.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "plex" / "libraries.yml"


@dataclass(frozen=True)
class Action:
    kind: str  # "add-library" | "library-drift" | "setting-drift"
    name: str
    detail: str


def load_config(path: Path = CONFIG) -> dict:
    with path.open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    for library in config["libraries"]:
        for key in ("name", "type", "agent", "scanner", "language", "locations"):
            if not library.get(key):
                raise ValueError(f"library {library.get('name')!r} lacks {key}")
    return config


def diff(config: dict, sections: list[dict], settings: dict) -> list[Action]:
    """Pure comparison. sections: [{name, type, locations}], settings: {id: value}."""
    actions = []
    existing = {s["name"]: s for s in sections}
    for library in config["libraries"]:
        have = existing.get(library["name"])
        if have is None:
            actions.append(Action("add-library", library["name"], ", ".join(library["locations"])))
            continue
        if have["type"] != library["type"]:
            actions.append(
                Action("library-drift", library["name"], f"type {have['type']} != {library['type']}")
            )
        missing = sorted(set(library["locations"]) - set(have["locations"]))
        if missing:
            actions.append(Action("library-drift", library["name"], f"missing locations {missing}"))
    for key, want in (config.get("settings") or {}).items():
        if key in settings and settings[key] != want:
            actions.append(Action("setting-drift", key, f"{settings[key]!r} != {want!r}"))
    return actions


def apply_allowed(config: dict, env=os.environ) -> bool:
    return env.get("PLEX_ALLOW_APPLY") == "true" and env.get("PLEX_CONFIRMATION") == (
        f"PLEX LIBRARIES {config['server']}"
    )


def connect(env=os.environ):
    from plexapi.server import PlexServer  # imported lazily: tests need no plexapi

    token = env.get("PLEX_TOKEN")
    if not token:
        raise SystemExit("set PLEX_TOKEN (operator input); it is never printed")
    return PlexServer(env.get("PLEX_URL", "http://127.0.0.1:32400"), token)


def read_state(server) -> tuple[list[dict], dict]:
    sections = [
        {"name": s.title, "type": s.type, "locations": list(s.locations)} for s in server.library.sections()
    ]
    settings = {s.id: s.value for s in server.settings.all()}
    return sections, settings


def add_libraries(server, config: dict, actions: list[Action]) -> None:
    wanted = {a.name for a in actions if a.kind == "add-library"}
    for library in config["libraries"]:
        if library["name"] in wanted:
            server.library.add(
                name=library["name"],
                type=library["type"],
                agent=library["agent"],
                scanner=library["scanner"],
                location=library["locations"],
                language=library["language"],
            )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", nargs="?", choices=["plan", "check"], default="plan")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    config = load_config()
    if args.apply and not apply_allowed(config):
        print(
            f'refusing: set PLEX_ALLOW_APPLY=true and PLEX_CONFIRMATION="PLEX LIBRARIES {config["server"]}"'
        )
        return 2
    server = connect()
    if args.mode == "check":
        print(f"Plex answers: version {server.version}")
        return 0
    actions = diff(config, *read_state(server))
    for action in actions:
        print(f"{action.kind}: {action.name}: {action.detail}")
    if not actions:
        print("Plex matches config/plex/libraries.yml")
    if args.apply:
        add_libraries(server, config, actions)
        print("added missing libraries; drift items above need an operator decision")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
