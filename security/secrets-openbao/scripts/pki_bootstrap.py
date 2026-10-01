#!/usr/bin/env python3
"""Create the offline bootstrap CA and three node certificates outside Git.

The operator must move the root key to offline custody after certificate
issuance. This script never prints private material.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NODES = {
    "bao-1": "192.168.0.41",
    "bao-2": "192.168.0.42",
    "bao-3": "192.168.0.43",
}
VIP_NAME = "bao.lab.example.com"
VIP_ADDRESS = "192.168.0.40"


def run(command: list[str]) -> None:
    subprocess.run(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != "CREATE OFFLINE OPENBAO ROOT CA":
        print("exact PKI confirmation is required", file=sys.stderr)
        return 2
    output = args.output.expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if output == repository_root or repository_root in output.parents:
        print("PKI output must be outside the repository", file=sys.stderr)
        return 2
    if output.exists() and any(output.iterdir()):
        print(
            "output directory is not empty; refusing to overwrite PKI material",
            file=sys.stderr,
        )
        return 2
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(output, 0o700)

    root_key = output / "offline-root-key.pem"
    root_cert = output / "ca.pem"
    try:
        run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:4096",
                "-out",
                str(root_key),
            ]
        )
        root_key.chmod(0o600)
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-new",
                "-sha256",
                "-days",
                "3650",
                "-key",
                str(root_key),
                "-out",
                str(root_cert),
                "-subj",
                "/O=ExampleLab Home Lab/CN=Home Lab Offline Root CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE,pathlen:1",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            ]
        )
        root_cert.chmod(0o644)

        with tempfile.TemporaryDirectory(prefix="openbao-pki-") as directory:
            work = Path(directory)
            for node, address in NODES.items():
                key = output / f"{node}-key.pem"
                cert = output / f"{node}.pem"
                csr = work / f"{node}.csr"
                extensions = work / f"{node}.ext"
                run(
                    [
                        "openssl",
                        "genpkey",
                        "-algorithm",
                        "EC",
                        "-pkeyopt",
                        "ec_paramgen_curve:P-256",
                        "-out",
                        str(key),
                    ]
                )
                key.chmod(0o600)
                run(
                    [
                        "openssl",
                        "req",
                        "-new",
                        "-key",
                        str(key),
                        "-out",
                        str(csr),
                        "-subj",
                        f"/O=ExampleLab Home Lab/CN={node}.lab.example.com",
                    ]
                )
                write_private(
                    extensions,
                    "\n".join(
                        (
                            "basicConstraints=critical,CA:FALSE",
                            "keyUsage=critical,digitalSignature,keyEncipherment",
                            "extendedKeyUsage=serverAuth,clientAuth",
                            f"subjectAltName=DNS:{node}.lab.example.com,DNS:{VIP_NAME},IP:{address},IP:{VIP_ADDRESS}",
                            "subjectKeyIdentifier=hash",
                            "authorityKeyIdentifier=keyid,issuer",
                        )
                    )
                    + "\n",
                )
                run(
                    [
                        "openssl",
                        "x509",
                        "-req",
                        "-sha256",
                        "-days",
                        "397",
                        "-in",
                        str(csr),
                        "-CA",
                        str(root_cert),
                        "-CAkey",
                        str(root_key),
                        "-CAcreateserial",
                        "-out",
                        str(cert),
                        "-extfile",
                        str(extensions),
                    ]
                )
                cert.chmod(0o644)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"PKI generation failed: {type(exc).__name__}", file=sys.stderr)
        return 3

    print(
        f"created bootstrap certificates in {output}; move offline-root-key.pem to offline custody"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
