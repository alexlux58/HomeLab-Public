#!/usr/bin/env python3
"""Reconcile non-secret OpenBao configuration through its HTTP API.

The operator token is read from a protected file and is never emitted. This
program never writes application secret values or creates AppRole SecretIDs.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


class BaoError(RuntimeError):
    """An OpenBao request failed without exposing its response body."""


class BaoClient:
    def __init__(self, address: str, ca_cert: Path, token: str) -> None:
        self.address = address.rstrip("/")
        self.context = ssl.create_default_context(cafile=str(ca_cert))
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        expected: tuple[int, ...] = (200, 204),
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.address}/v1/{path.lstrip('/')}",
            data=body,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Vault-Token": self.token,
            },
        )
        try:
            with urllib.request.urlopen(
                request, context=self.context, timeout=15
            ) as response:
                raw = response.read()
                if response.status not in expected:
                    raise BaoError(
                        f"unexpected HTTP status {response.status} for {path}"
                    )
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise BaoError(f"HTTP status {exc.code} for {method} {path}") from None
        except urllib.error.URLError as exc:
            raise BaoError(f"connection failed for {path}: {exc.reason}") from None


def load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def ensure_engines(client: BaoClient, root: Path, actions: list[str]) -> None:
    desired = load_json(root / "openbao/secrets-engines/engines.json")
    mounts = client.request("GET", "sys/mounts").get("data", {})
    if not isinstance(mounts, dict):
        raise BaoError("sys/mounts returned an invalid response")
    for path, config in desired.items():
        mount_path = f"{path.rstrip('/')}/"
        if mount_path not in mounts:
            client.request("POST", f"sys/mounts/{path}", config)
            actions.append(f"enabled secrets engine {path}")
        else:
            actions.append(f"verified secrets engine {path}")


def ensure_policies(client: BaoClient, root: Path, actions: list[str]) -> None:
    for policy_file in sorted((root / "openbao/policies").glob("*.hcl")):
        name = policy_file.stem
        desired = policy_file.read_text(encoding="utf-8").strip()
        current = ""
        try:
            response = client.request("GET", f"sys/policies/acl/{name}")
            current = str(response.get("data", {}).get("rules", "")).strip()
        except BaoError:
            current = ""
        if current != desired:
            client.request("PUT", f"sys/policies/acl/{name}", {"policy": desired})
            actions.append(f"updated policy {name}")
        else:
            actions.append(f"verified policy {name}")


def ensure_auth(client: BaoClient, root: Path, actions: list[str]) -> None:
    auth_methods = client.request("GET", "sys/auth").get("data", {})
    if not isinstance(auth_methods, dict):
        raise BaoError("sys/auth returned an invalid response")
    if "approle/" not in auth_methods:
        client.request("POST", "sys/auth/approle", {"type": "approle"})
        actions.append("enabled AppRole auth")
    else:
        actions.append("verified AppRole auth")

    roles = load_json(root / "openbao/auth/approle-roles.json")
    for name, payload in roles.items():
        client.request("POST", f"auth/approle/role/{name}", payload)
        actions.append(f"reconciled AppRole {name} without creating a SecretID")


def planned_actions(root: Path, phase: str) -> list[str]:
    actions: list[str] = []
    if phase in {"engines", "all"}:
        engines = load_json(root / "openbao/secrets-engines/engines.json")
        actions.extend(f"would reconcile secrets engine {name}" for name in engines)
    if phase in {"policies", "all"}:
        actions.extend(
            f"would reconcile policy {path.stem}"
            for path in sorted((root / "openbao/policies").glob("*.hcl"))
        )
    if phase in {"auth", "all"}:
        roles = load_json(root / "openbao/auth/approle-roles.json")
        actions.extend(f"would reconcile AppRole {name}" for name in roles)
    return actions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--phase", choices=("engines", "policies", "auth", "all"), required=True
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if args.dry_run:
        print(
            json.dumps(
                {"status": "planned", "actions": planned_actions(root, args.phase)},
                indent=2,
            )
        )
        return 0
    if args.token_file is None or not args.token_file.is_file():
        print("operator token file is missing", file=sys.stderr)
        return 2
    if not args.ca_cert.is_file():
        print("CA certificate is missing", file=sys.stderr)
        return 2
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        print("operator token file is empty", file=sys.stderr)
        return 2

    client = BaoClient(args.address, args.ca_cert, token)
    actions: list[str] = []
    try:
        if args.phase in {"engines", "all"}:
            ensure_engines(client, root, actions)
        if args.phase in {"policies", "all"}:
            ensure_policies(client, root, actions)
        if args.phase in {"auth", "all"}:
            ensure_auth(client, root, actions)
    except BaoError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps({"status": "reconciled", "actions": actions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
